"""
CoreKorean MCP Server
A session-focused Korean vocabulary tutor with optional YouTube support.

Tools:
  - get_vocab_session          -> pick 14 words from the vocab bank
  - get_module_vocab           -> return all words for a selected module
  - generate_quiz              -> build a randomized 14-question quiz from those words
  - check_answer               -> score a learner's answer and return plain feedback
  - explain_quiz_answer        -> score an answer and return supportive AI feedback
  - get_youtube_recommendation -> search YouTube for pronunciation/usage help
  - enrich_youtube_links       -> save verified YouTube results to a new JSON file

Run:
  python server.py

Optional: set YOUTUBE_API_KEY in your environment to use the YouTube Data API.
If it is not set, YouTube tools return search URLs instead of saved video links.

Optional: set GEMINI_API_KEY in your environment to use Gemini-powered feedback
for explain_quiz_answer.
"""

import html
import json
import os
import random
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from fastmcp import FastMCP

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# -- Data ---------------------------------------------------------------------

if load_dotenv:
    load_dotenv()

VOCAB_PATH = Path(__file__).parent / "vocab_bank.json"
ENRICHED_VOCAB_PATH = Path(__file__).parent / "vocab_bank_enriched.json"

with VOCAB_PATH.open(encoding="utf-8") as f:
    VOCAB_BANK: dict[str, Any] = json.load(f)

VALID_LEVELS = list(VOCAB_BANK.keys())  # ["beginner", "intermediate"]
VALID_TOPICS = ["food", "travel", "daily_life", "testing_empty", "any"]
QUESTION_TYPES = ["multiple_choice", "fill_blank", "translate"]
SESSION_SIZE = 14
QUIZ_SIZE = 14

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-2.5-flash")

mcp = FastMCP("CoreKorean")

# -- Helpers ------------------------------------------------------------------


def _pool(level: str, topic: str) -> list[dict[str, Any]]:
    level_data = VOCAB_BANK.get(level, {})
    if topic == "any":
        words: list[dict[str, Any]] = []
        for bucket in level_data.values():
            words.extend(bucket)
        return words
    return level_data.get(topic, [])


def _all_words(level: str | None = None) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    levels = [level] if level else VALID_LEVELS
    for level_name in levels:
        for bucket in VOCAB_BANK.get(level_name, {}).values():
            words.extend(bucket)
    return words


def _module_pool(module: int, level: str = "beginner") -> list[dict[str, Any]]:
    return [w for w in _all_words(level) if int(w.get("module", -1)) == module]


def _normalize(s: str) -> str:
    """Lowercase and strip punctuation for loose answer comparison."""
    return re.sub(r"[^\w\s]", "", s).lower().strip()


def _youtube_query(word: dict[str, Any], search_type: str = "pronunciation") -> str:
    korean = word.get("korean", "").strip()
    english = word.get("english", "").strip()
    romanization = word.get("romanization", "").strip()

    if search_type == "usage":
        return f"Korean {korean} {english} example sentence beginner"
    return f"Korean pronunciation {korean} {romanization} {english} beginner"


def _youtube_search_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def _word_response(word: dict[str, Any], word_id: str | None = None) -> dict[str, Any]:
    query = _youtube_query(word)
    media = word.get("media", {}) or {}
    youtube = media.get("youtube", {}) or {}

    result = {
        "korean": word["korean"],
        "romanization": word["romanization"],
        "english": word["english"],
        "part_of_speech": word["part_of_speech"],
        "example": word["example"],
        "module": word["module"],
        "module_name": word["module_name"],
        "media": {
            "youtube_query": youtube.get("query", query),
            "youtube_search_url": youtube.get("search_url", _youtube_search_url(query)),
            "youtube_verified": bool(youtube.get("verified", False)),
            "youtube_url": youtube.get("url"),
            "youtube_title": youtube.get("title"),
            "youtube_channel": youtube.get("channel"),
        },
    }
    if word_id:
        result["id"] = word_id
    return result


def _search_youtube_video(query: str, max_results: int = 1) -> dict[str, Any]:
    if not YOUTUBE_API_KEY:
        return {
            "verified": False,
            "query": query,
            "search_url": _youtube_search_url(query),
            "note": "No YOUTUBE_API_KEY found. Returning a search URL instead.",
        }

    api_url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&q={quote_plus(query)}&type=video&maxResults={max_results}"
        f"&relevanceLanguage=ko&safeSearch=strict&key={YOUTUBE_API_KEY}"
    )
    with urllib.request.urlopen(api_url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data.get("items", [])
    if not items:
        return {
            "verified": False,
            "query": query,
            "search_url": _youtube_search_url(query),
            "note": "No YouTube video result found.",
        }

    item = items[0]
    video_id = item["id"]["videoId"]
    snippet = item["snippet"]
    return {
        "verified": True,
        "query": query,
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": html.unescape(snippet.get("title", "")),
        "channel": html.unescape(snippet.get("channelTitle", "")),
        "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
        "search_url": _youtube_search_url(query),
    }


def _validate_question(question: dict[str, Any]) -> str | None:
    if not question:
        return "question is required."

    missing = {"question_id", "type", "answer", "korean_word"} - question.keys()
    if missing:
        return f"question is missing fields: {missing}"

    return None


def _grade_quiz_answer(question: dict[str, Any], user_answer: str) -> dict[str, Any]:
    question_error = _validate_question(question)
    if question_error:
        return {"error": question_error}

    if not user_answer or not user_answer.strip():
        return {"error": "user_answer cannot be empty."}

    cleaned_user_answer = user_answer.strip()
    correct_answer = str(question["answer"]).strip()
    is_correct = _normalize(cleaned_user_answer) == _normalize(correct_answer)

    return {
        "question_id": question["question_id"],
        "is_correct": is_correct,
        "user_answer": cleaned_user_answer,
        "correct_answer": correct_answer,
        "score_delta": 10 if is_correct else 0,
    }


def _feedback_context(
    question: dict[str, Any],
    vocab_word: dict[str, Any] | None = None,
) -> dict[str, str]:
    vocab_word = vocab_word or {}
    return {
        "question_type": str(question.get("type", "")).strip(),
        "prompt": str(question.get("prompt", "")).strip(),
        "korean_word": str(
            vocab_word.get("korean") or question.get("korean_word", "")
        ).strip(),
        "english": str(
            vocab_word.get("english") or question.get("answer", "")
        ).strip(),
        "romanization": str(vocab_word.get("romanization", "")).strip(),
        "part_of_speech": str(vocab_word.get("part_of_speech", "")).strip(),
        "example": str(vocab_word.get("example", "")).strip(),
        "module_name": str(vocab_word.get("module_name", "")).strip(),
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Gemini response did not contain a JSON object.")

    return json.loads(match.group(0))


def _generate_quiz_feedback_with_gemini(
    *,
    question: dict[str, Any],
    user_answer: str,
    grading: dict[str, Any],
    vocab_word: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if genai is None:
        raise RuntimeError(
            "google-generativeai is not installed. Install it to use explain_quiz_answer."
        )
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    context = _feedback_context(question, vocab_word)

    prompt = f"""
You are helping a beginner learn Korean vocabulary.

Write beginner-friendly English only.
Be supportive, concise, and clear.
Use only the vocabulary and question context below.
Do not introduce unrelated Korean words.
Do not give advanced grammar explanations.
Return JSON only.
Do not use markdown.

Question context:
{json.dumps(context, ensure_ascii=False, indent=2)}

Learner answer context:
{json.dumps({
    "question_id": grading["question_id"],
    "user_answer": grading["user_answer"],
    "correct_answer": grading["correct_answer"],
    "is_correct": grading["is_correct"],
}, ensure_ascii=False, indent=2)}

Return exactly this JSON shape:
{{
  "short_feedback": "...",
  "why_wrong": "...",
  "memory_tip": "...",
  "practice_reminder": "..."
}}

Rules:
- If is_correct is true:
  - short_feedback should praise the learner briefly.
  - why_wrong should be an empty string.
  - memory_tip should help them remember the correct answer.
  - practice_reminder should be one short practice suggestion.
- If is_correct is false:
  - short_feedback should gently say the answer was not correct.
  - why_wrong should explain simply why the learner's answer does not match the correct answer.
  - memory_tip should give one simple memory trick or mnemonic tied only to the provided word/context.
  - practice_reminder should be one short suggestion for review.
- Keep each field short. 1 to 2 sentences max.
""".strip()

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.3},
    )

    feedback = _parse_json_object(response.text)

    return {
        "short_feedback": str(feedback.get("short_feedback", "")).strip(),
        "why_wrong": str(feedback.get("why_wrong", "")).strip(),
        "memory_tip": str(feedback.get("memory_tip", "")).strip(),
        "practice_reminder": str(feedback.get("practice_reminder", "")).strip(),
    }


# -- Tool 1: get_vocab_session -------------------------------------------------


@mcp.tool()
def get_vocab_session(
    level: str = "beginner",
    topic: str = "any",
    module: int | None = None,
) -> dict[str, Any]:
    """
    Return 14 Korean vocabulary words for a learning session.

    Each word includes its Korean script, romanization, English meaning,
    part of speech, example sentence, module info, and media fields.

    Args:
        level: 'beginner' or 'intermediate'
        topic: 'food', 'travel', 'daily_life', or 'any'
        module: Optional module number. If provided, it overrides topic.

    Returns:
        session_id, level, topic, word_count, and a list of word objects.
    """
    level = level.lower().strip()
    topic = topic.lower().strip().replace(" ", "_")

    if level not in VALID_LEVELS:
        return {"error": f"Invalid level '{level}'. Choose from: {', '.join(VALID_LEVELS)}."}
    if topic not in VALID_TOPICS:
        return {"error": f"Invalid topic '{topic}'. Choose from: {', '.join(VALID_TOPICS)}."}

    pool = _module_pool(module, level) if module is not None else _pool(level, topic)
    if not pool:
        return {"error": f"No words found for level='{level}', topic='{topic}', module='{module}'."}

    selected = random.sample(pool, min(SESSION_SIZE, len(pool)))
    session_id = str(uuid.uuid4())[:8]

    words = [
        _word_response(w, word_id=f"{session_id}_w{i}")
        for i, w in enumerate(selected)
    ]

    return {
        "session_id": session_id,
        "level": level,
        "topic": topic,
        "module": module,
        "word_count": len(words),
        "words": words,
    }


# -- Tool 2: get_module_vocab --------------------------------------------------


@mcp.tool()
def get_module_vocab(
    module: int,
    level: str = "beginner",
) -> dict[str, Any]:
    """
    Return the full vocabulary list for one module.

    Use this when the lesson should follow the module order from the course.
    """
    level = level.lower().strip()
    if level not in VALID_LEVELS:
        return {"error": f"Invalid level '{level}'. Choose from: {', '.join(VALID_LEVELS)}."}

    words = _module_pool(module, level)
    if not words:
        return {"error": f"No words found for level='{level}', module='{module}'."}

    words = sorted(words, key=lambda w: w["korean"])
    module_name = words[0].get("module_name", "")
    return {
        "level": level,
        "module": module,
        "module_name": module_name,
        "word_count": len(words),
        "words": [_word_response(w) for w in words],
    }


# -- Tool 3: generate_quiz -----------------------------------------------------


@mcp.tool()
def generate_quiz(
    vocab_list: list[dict[str, Any]],
    question_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate a randomized 14-question quiz from a vocabulary session.

    Question types:
      - multiple_choice  Korean word -> pick the correct English meaning
      - fill_blank       English meaning -> type the Korean word
      - translate        Korean word + romanization -> type the English meaning

    Args:
        vocab_list:     The 'words' list from get_vocab_session.
        question_types: List of types to use. Defaults to all three.

    Returns:
        quiz_id, question_count, and a list of question objects.
    """
    if not vocab_list:
        return {"error": "vocab_list is empty. Call get_vocab_session first."}
    if len(vocab_list) < 4:
        return {"error": "Need at least 4 words to generate a quiz with distractors."}

    if not question_types:
        question_types = QUESTION_TYPES
    else:
        invalid = [qt for qt in question_types if qt not in QUESTION_TYPES]
        if invalid:
            return {"error": f"Unknown question type(s): {invalid}. Valid: {QUESTION_TYPES}."}

    quiz_id = str(uuid.uuid4())[:8]
    words = random.sample(vocab_list, min(QUIZ_SIZE, len(vocab_list)))
    questions: list[dict[str, Any]] = []

    for i, word in enumerate(words):
        q_type = question_types[i % len(question_types)]
        q_id = f"{quiz_id}_q{i + 1}"
        others = [w for w in vocab_list if w["korean"] != word["korean"]]

        if q_type == "multiple_choice":
            distractors = random.sample(others, min(3, len(others)))
            options = [word["english"]] + [d["english"] for d in distractors]
            random.shuffle(options)
            questions.append(
                {
                    "question_id": q_id,
                    "type": "multiple_choice",
                    "prompt": f"What does '{word['korean']}' ({word['romanization']}) mean?",
                    "options": options,
                    "answer": word["english"],
                    "korean_word": word["korean"],
                }
            )

        elif q_type == "fill_blank":
            questions.append(
                {
                    "question_id": q_id,
                    "type": "fill_blank",
                    "prompt": f"Type the Korean word for: {word['english']}",
                    "hint": f"Romanization: {word['romanization']}",
                    "options": None,
                    "answer": word["korean"],
                    "korean_word": word["korean"],
                }
            )

        else:  # translate
            questions.append(
                {
                    "question_id": q_id,
                    "type": "translate",
                    "prompt": f"Translate into English: {word['korean']} ({word['romanization']})",
                    "options": None,
                    "answer": word["english"],
                    "korean_word": word["korean"],
                }
            )

    return {
        "quiz_id": quiz_id,
        "question_count": len(questions),
        "questions": questions,
    }


# -- Tool 4: check_answer ------------------------------------------------------


@mcp.tool()
def check_answer(
    question: dict[str, Any],
    user_answer: str,
) -> dict[str, Any]:
    """
    Score a learner's answer to a quiz question.

    Comparison is case-insensitive and punctuation-tolerant.
    Returns whether the answer is correct, the right answer if not,
    and the point value earned for this question (10 if correct, 0 if not).

    Args:
        question:    A question object from generate_quiz.
        user_answer: The learner's submitted answer.

    Returns:
        question_id, is_correct, user_answer, correct_answer, score_delta.
    """
    result = _grade_quiz_answer(question, user_answer)
    if "error" in result:
        return result

    if not result["is_correct"]:
        result["feedback"] = f"The correct answer is '{result['correct_answer']}'."

    return result


# -- Tool 4b: explain_quiz_answer ----------------------------------------------


@mcp.tool()
def explain_quiz_answer(
    question: dict[str, Any],
    user_answer: str,
    vocab_word: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Explain a learner's quiz answer with supportive AI feedback.

    This uses the same loose comparison logic as check_answer, then asks Gemini
    for a short beginner-friendly explanation, memory tip, and practice reminder.

    Args:
        question:    A question object from generate_quiz.
        user_answer: The learner's submitted answer.
        vocab_word:  Optional original vocab word object for extra context.

    Returns:
        Structured feedback JSON for the learner.
    """
    grading = _grade_quiz_answer(question, user_answer)
    if "error" in grading:
        return grading

    try:
        feedback = _generate_quiz_feedback_with_gemini(
            question=question,
            user_answer=user_answer,
            grading=grading,
            vocab_word=vocab_word,
        )
    except Exception as e:
        return {
            "question_id": grading["question_id"],
            "is_correct": grading["is_correct"],
            "user_answer": grading["user_answer"],
            "correct_answer": grading["correct_answer"],
            "short_feedback": (
                "Nice work." if grading["is_correct"] else "Not quite this time."
            ),
            "why_wrong": (
                ""
                if grading["is_correct"]
                else f"Your answer does not match the expected answer '{grading['correct_answer']}'."
            ),
            "memory_tip": "Say the correct answer out loud and review it again later today.",
            "practice_reminder": "Try this word again after a short break.",
            "error": f"Gemini feedback generation failed: {e}",
        }

    return {
        "question_id": grading["question_id"],
        "is_correct": grading["is_correct"],
        "user_answer": grading["user_answer"],
        "correct_answer": grading["correct_answer"],
        "short_feedback": feedback["short_feedback"],
        "why_wrong": feedback["why_wrong"],
        "memory_tip": feedback["memory_tip"],
        "practice_reminder": feedback["practice_reminder"],
    }


# -- Tool 5: get_youtube_recommendation ----------------------------------------


@mcp.tool()
def get_youtube_recommendation(
    korean_word: str,
    english_meaning: str = "",
    romanization: str = "",
    search_type: str = "pronunciation",
) -> dict[str, Any]:
    """
    Return a YouTube recommendation for a Korean word.

    If YOUTUBE_API_KEY is set, this returns a real video result from the
    YouTube Data API. If not, it returns a YouTube search URL.
    """
    if not korean_word or not korean_word.strip():
        return {"error": "korean_word is required."}

    word = {
        "korean": korean_word.strip(),
        "english": english_meaning.strip(),
        "romanization": romanization.strip(),
    }
    search_type = search_type.lower().strip()
    query = _youtube_query(word, search_type)

    try:
        return {
            "korean_word": word["korean"],
            "search_type": search_type,
            **_search_youtube_video(query),
        }
    except Exception as e:
        return {
            "korean_word": word["korean"],
            "verified": False,
            "query": query,
            "search_url": _youtube_search_url(query),
            "error": f"YouTube lookup failed: {e}",
        }


# -- Tool 6: enrich_youtube_links ----------------------------------------------


@mcp.tool()
def enrich_youtube_links(
    module: int | None = None,
    level: str = "beginner",
    search_type: str = "pronunciation",
    output_path: str = "",
) -> dict[str, Any]:
    """
    Create an enriched vocabulary JSON with YouTube links.

    This only writes direct video links when YOUTUBE_API_KEY is set and the
    YouTube Data API returns a real result. Without the API key, it returns
    search URLs and leaves the JSON file unchanged.
    """
    level = level.lower().strip()
    search_type = search_type.lower().strip()

    if level not in VALID_LEVELS:
        return {"error": f"Invalid level '{level}'. Choose from: {', '.join(VALID_LEVELS)}."}

    targets = _module_pool(module, level) if module is not None else _all_words(level)
    if not targets:
        return {"error": f"No words found for level='{level}', module='{module}'."}

    if not YOUTUBE_API_KEY:
        preview = []
        for word in targets:
            query = _youtube_query(word, search_type)
            preview.append(
                {
                    "korean": word["korean"],
                    "query": query,
                    "search_url": _youtube_search_url(query),
                }
            )
        return {
            "verified": False,
            "updated_count": 0,
            "message": "No YOUTUBE_API_KEY found. No video links were written.",
            "preview": preview,
        }

    source_bank = VOCAB_BANK
    if ENRICHED_VOCAB_PATH.exists() and not output_path:
        with ENRICHED_VOCAB_PATH.open(encoding="utf-8") as f:
            source_bank = json.load(f)

    enriched = json.loads(json.dumps(source_bank, ensure_ascii=False))
    updated_count = 0
    errors: list[dict[str, str]] = []

    for level_name, level_data in enriched.items():
        if level_name != level:
            continue
        for bucket in level_data.values():
            for word in bucket:
                if module is not None and int(word.get("module", -1)) != module:
                    continue
                query = _youtube_query(word, search_type)
                try:
                    youtube = _search_youtube_video(query)
                    word.setdefault("media", {})["youtube"] = youtube
                    if youtube.get("verified"):
                        updated_count += 1
                except Exception as e:
                    errors.append({"korean": str(word.get("korean", "")), "error": str(e)})

    destination = Path(output_path) if output_path else ENRICHED_VOCAB_PATH
    with destination.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    return {
        "verified": len(errors) == 0,
        "output_path": str(destination),
        "updated_count": updated_count,
        "error_count": len(errors),
        "errors": errors[:10],
    }


if __name__ == "__main__":
    mcp.run()