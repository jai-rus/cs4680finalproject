import random
import re
import uuid
from typing import Any


VALID_QUESTION_TYPES = ["multiple_choice", "fill_blank", "translate"]
DEFAULT_QUIZ_SIZE = 14


def normalize_answer(value: str) -> str:
    """Make answer checks forgiving about case and punctuation."""
    return re.sub(r"[^\w\s]", "", value).lower().strip()


def build_quiz(
    vocab_list: list[dict],
    all_words: list[dict] | None = None,
    count: int = DEFAULT_QUIZ_SIZE,
    question_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build quiz questions from vocabulary words.

    The web app and the MCP server both use this function so their quizzes stay
    consistent.
    """
    if not vocab_list:
        raise ValueError("vocab_list is empty.")
    if len(vocab_list) < 4:
        raise ValueError("Need at least 4 words to generate a quiz with distractors.")

    if question_types is None:
        question_types = ["multiple_choice"]
    invalid = [qt for qt in question_types if qt not in VALID_QUESTION_TYPES]
    if invalid:
        raise ValueError(f"Unknown question type(s): {invalid}. Valid: {VALID_QUESTION_TYPES}.")

    all_words = all_words or vocab_list
    quiz_id = str(uuid.uuid4())[:8]
    selected = random.sample(vocab_list, min(count, len(vocab_list)))
    questions = []

    for index, word in enumerate(selected, start=1):
        q_type = question_types[(index - 1) % len(question_types)]
        question_id = f"{quiz_id}_q{index}"

        if q_type == "multiple_choice":
            distractor_pool = [
                item for item in all_words
                if item.get("korean") != word.get("korean")
            ]
            distractors = random.sample(distractor_pool, min(3, len(distractor_pool)))
            options = [word["english"]] + [item["english"] for item in distractors]
            random.shuffle(options)
            questions.append({
                "id": f"q{index}",
                "question_id": question_id,
                "type": "multiple_choice",
                "prompt": f"What does '{word['korean']}' ({word.get('romanization', '')}) mean?",
                "options": options,
                "answer": word["english"],
                "korean": word["korean"],
                "korean_word": word["korean"],
            })
            continue

        if q_type == "fill_blank":
            questions.append({
                "id": f"q{index}",
                "question_id": question_id,
                "type": "fill_blank",
                "prompt": f"Type the Korean word for: {word['english']}",
                "hint": f"Romanization: {word.get('romanization', '')}",
                "options": None,
                "answer": word["korean"],
                "korean": word["korean"],
                "korean_word": word["korean"],
            })
            continue

        questions.append({
            "id": f"q{index}",
            "question_id": question_id,
            "type": "translate",
            "prompt": f"Translate into English: {word['korean']} ({word.get('romanization', '')})",
            "options": None,
            "answer": word["english"],
            "korean": word["korean"],
            "korean_word": word["korean"],
        })

    return {
        "quiz_id": quiz_id,
        "question_count": len(questions),
        "questions": questions,
    }


def check_quiz_answer(question: dict, user_answer: str) -> dict[str, Any]:
    """Check one quiz answer and return simple feedback."""
    if not question:
        return {"error": "question is required."}
    if not user_answer or not user_answer.strip():
        return {"error": "user_answer cannot be empty."}

    missing = {"type", "answer"} - question.keys()
    if missing:
        return {"error": f"question is missing fields: {missing}"}

    user_answer = user_answer.strip()
    correct_answer = str(question["answer"])
    is_correct = normalize_answer(user_answer) == normalize_answer(correct_answer)

    result: dict[str, Any] = {
        "question_id": question.get("question_id", question.get("id", "")),
        "is_correct": is_correct,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "score_delta": 10 if is_correct else 0,
    }

    if is_correct:
        result["feedback"] = "Correct."
    else:
        result["feedback"] = f"The correct answer is '{correct_answer}'."

    return result
