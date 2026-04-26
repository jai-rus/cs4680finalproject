from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
import os
import json
import uuid
import re
from pathlib import Path
from quiz_utils import build_quiz, check_quiz_answer

load_dotenv()

app = FastAPI()

STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

sessions = {}
vocab_store = []
module_store = {}

# PDF chunks are kept in memory for this small class project.
doc_chunks = []

class LessonRequest(BaseModel):
    session_id: str
    topic: str = Field(min_length=1)
    k: int = 14

class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = 14

class RagContextRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = 3

class AnswerRequest(BaseModel):
    question: dict
    user_answer: str = Field(min_length=1)

@app.get("/")
def root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "CoreKorean API is running"}

@app.post("/session")
def create_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = []
    return {"session_id": session_id}

@app.post("/ingest-vocab")
def ingest_vocab():
    global vocab_store, module_store

    if vocab_store:
        return {
            "message": "Vocabulary already ingested. Skipping reload.",
            "words_loaded": len(vocab_store),
            "modules_loaded": list(module_store.keys())
        }

    try:
        vocab_path = get_vocab_path()
        if not vocab_path.exists():
            vocab_path = Path("data/vocab.json")

        with vocab_path.open("r", encoding="utf-8") as f:
            raw_vocab = json.load(f)

        vocab_store = flatten_vocab(raw_vocab)

        module_store = {}

        for item in vocab_store:
            module = item["module_name"]

            if module not in module_store:
                module_store[module] = []

            module_store[module].append(item)

        return {
            "message": "Vocabulary ingested successfully",
            "source_file": str(vocab_path),
            "words_loaded": len(vocab_store),
            "modules_loaded": list(module_store.keys())
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Could not find file."
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest-docs")
def ingest_docs():
    global doc_chunks

    if doc_chunks:
        return {
            "message": "Course documents already ingested. Skipping reload.",
            "chunks_loaded": len(doc_chunks),
            "sources": sorted({chunk["source"] for chunk in doc_chunks}),
        }

    try:
        pdf_paths = [
            Path("Korean_Vocabulary_140_Final.pdf"),
        ]
        loaded = []
        for path in pdf_paths:
            if not path.exists():
                continue
            text = extract_pdf_text(path)

            # Split the PDF text so the lesson prompt stays short.
            for index, chunk_text in enumerate(chunk_text_by_words(text)):
                loaded.append({
                    "id": f"{path.stem}-{index + 1}",
                    "source": path.name,
                    "text": chunk_text,
                })

        doc_chunks = loaded
        return {
            "message": "Course documents ingested successfully",
            "chunks_loaded": len(doc_chunks),
            "sources": sorted({chunk["source"] for chunk in doc_chunks}),
        }

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pypdf is not installed. Run pip install -r requirements.txt."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def flatten_vocab(raw_vocab):
    if isinstance(raw_vocab, list):
        return [
            {
                "module": item.get("module"),
                "module_name": item.get("module_name", item.get("module", "")),
                "korean": item["korean"],
                "romanization": item.get("romanization", ""),
                "english": item["english"],
                "part_of_speech": item.get("part_of_speech", ""),
                "example": item.get("example", {}),
                "media": item.get("media", {}),
            }
            for item in raw_vocab
        ]

    words = []
    for level_data in raw_vocab.values():
        for bucket in level_data.values():
            for item in bucket:
                words.append({
                    "module": item.get("module"),
                    "module_name": item.get("module_name", item.get("module", "")),
                    "korean": item["korean"],
                    "romanization": item.get("romanization", ""),
                    "english": item["english"],
                    "part_of_speech": item.get("part_of_speech", ""),
                    "example": item.get("example", {}),
                    "media": item.get("media", {}),
                })
    return words


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def chunk_text_by_words(text: str, chunk_size: int = 170, overlap: int = 35):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start = max(0, end - overlap)
    return chunks


def ensure_docs_loaded():
    if not doc_chunks:
        ingest_docs()


def query_terms(query: str):
    return [
        term for term in re.findall(r"[\w가-힣]+", query.lower())
        if len(term) > 1
    ]


def retrieve_course_context(query: str, k: int = 3):
    ensure_docs_loaded()
    terms = query_terms(query)
    if not terms:
        return doc_chunks[:k]

    # Simple keyword search is enough for this small PDF.
    scored = []
    for chunk in doc_chunks:
        text = chunk["text"].lower()
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]


def get_vocab_path():
    # vocab_bank.json is the final file with the YouTube links included.
    return Path("vocab_bank.json")


def ensure_vocab_loaded():
    if not vocab_store:
        ingest_vocab()


def public_word(item):
    youtube = item.get("media", {}).get("youtube", {})
    return {
        "module": item.get("module"),
        "module_name": item.get("module_name"),
        "korean": item.get("korean"),
        "romanization": item.get("romanization"),
        "english": item.get("english"),
        "part_of_speech": item.get("part_of_speech"),
        "example": item.get("example"),
        "youtube": {
            "verified": bool(youtube.get("verified")),
            "url": youtube.get("url"),
            "title": youtube.get("title"),
            "channel": youtube.get("channel"),
            "search_url": youtube.get("search_url"),
            "query": youtube.get("query"),
        },
    }


def module_matches(module_name: str, target: str) -> bool:
    return target.lower() in module_name.lower()


def get_genai_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_API_KEY is not set."
        )
    return genai.Client(api_key=api_key)


def find_vocab_for_question(question: dict):
    ensure_vocab_loaded()
    korean = question.get("korean") or question.get("korean_word")
    answer = question.get("answer")

    for item in vocab_store:
        if korean and item.get("korean") == korean:
            return item

    for item in vocab_store:
        if answer and item.get("english") == answer:
            return item

    return None


def template_answer_review(word: dict | None, result: dict) -> str:
    if not word:
        return result.get("feedback", "")

    example = word.get("example", {}) or {}
    if result.get("is_correct"):
        first = f"{word['korean']} means {word['english']}, so your answer was correct."
    else:
        first = f"{word['korean']} means {word['english']}, not {result.get('user_answer', 'that answer')}."

    if example.get("korean") and example.get("english"):
        return f"{first} Example: {example['korean']} = {example['english']}"
    return first


def first_two_sentences(text: str) -> str:
    sentences = re.findall(r"[^.!?]+[.!?]?", text.strip())
    trimmed = " ".join(sentence.strip() for sentence in sentences[:2]).strip()
    return trimmed or text.strip()


def generate_answer_review(word: dict | None, result: dict) -> tuple[str, str]:
    fallback = template_answer_review(word, result)
    if not word or not os.getenv("GOOGLE_API_KEY"):
        return fallback, "template"

    query = f"{word.get('korean', '')} {word.get('english', '')} {word.get('module_name', '')}"
    course_chunks = retrieve_course_context(query, 2)
    course_context = "\n\n".join(
        f"[{chunk['source']} / {chunk['id']}]\n{chunk['text'][:700]}"
        for chunk in course_chunks
    )
    example = word.get("example", {}) or {}

    prompt = f"""
Write exactly 2 short sentences for a beginner Korean learner.
Use simple English.
Do not add extra Korean words unless they are already provided.

Quiz result:
- Correct: {result.get("is_correct")}
- User answer: {result.get("user_answer")}
- Correct answer: {result.get("correct_answer")}

Vocabulary:
- Korean: {word.get("korean")}
- Romanization: {word.get("romanization")}
- English: {word.get("english")}
- Example: {example.get("korean", "")} = {example.get("english", "")}

Course context:
{course_context}
"""

    try:
        client = get_genai_client()
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt
        )
        review = first_two_sentences(response.text or "")
        return review or fallback, "gemini_rag"
    except Exception:
        return fallback, "template"


def retrieve_vocab(topic: str, k: int = 14):

    if not vocab_store:
        raise HTTPException(
            status_code=400,
            detail="Vocabulary not ingested yet. Call /ingest-vocab first."
        )

    topic_lower = topic.lower()

    module_keywords = {
        "greetings": "Greetings & Basics", "basic": "Greetings & Basics",
        "basics": "Greetings & Basics", "hello": "Greetings & Basics",
        "number": "Numbers", "numbers": "Numbers", "count": "Numbers",
        "food": "Food & Restaurant", "restaurant": "Food & Restaurant",
        "drink": "Food & Restaurant", "eating": "Food & Restaurant",
        "family": "Family & People", "people": "Family & People",
        "person": "Family & People",
        "place": "Location & Places", "places": "Location & Places",
        "location": "Location & Places", "school": "Location & Places",
        "home": "Location & Places",
        "day": "Days & Time", "days": "Days & Time",
        "time": "Days & Time", "week": "Days & Time",
        "verb": "Daily Verbs", "verbs": "Daily Verbs",
        "daily": "Daily Verbs", "actions": "Daily Verbs",
        "weather": "Weather & Seasons", "season": "Weather & Seasons",
        "seasons": "Weather & Seasons",
        "shopping": "Shopping & Money", "money": "Shopping & Money",
        "store": "Shopping & Money",
        "feeling": "Feelings & States", "feelings": "Feelings & States",
        "emotion": "Feelings & States", "states": "Feelings & States"
    }

    selected_module = None

    for keyword, module in module_keywords.items():
        if keyword in topic_lower:
            selected_module = module
            break

    if selected_module:
        module_matches_list = [
            item for item in vocab_store
            if module_matches(item["module_name"], selected_module)
        ]
        if module_matches_list:
            return module_matches_list[:k]

    # fallback: search in module names, Korean words, and English meanings
    matches = []

    for item in vocab_store:
        searchable_text = (
            f"{item['module']} {item['module_name']} "
            f"{item['korean']} {item['english']} {item.get('romanization', '')}"
        ).lower()

        if topic_lower in searchable_text:
            matches.append(item)

    if matches:
        return matches[:k]

    # final fallback: return first k words
    return vocab_store[:k]


@app.get("/api/modules")
def list_modules():
    ensure_vocab_loaded()
    modules = {}
    for item in vocab_store:
        module_number = item.get("module")
        if module_number not in modules:
            modules[module_number] = {
                "module": module_number,
                "module_name": item.get("module_name"),
                "word_count": 0,
            }
        modules[module_number]["word_count"] += 1

    return {
        "modules": [
            modules[key]
            for key in sorted(modules.keys(), key=lambda value: int(value))
        ]
    }


@app.get("/api/modules/{module}/words")
def get_module_words(module: int):
    ensure_vocab_loaded()
    words = [
        public_word(item)
        for item in vocab_store
        if int(item.get("module", -1)) == module
    ]
    if not words:
        raise HTTPException(status_code=404, detail="Module not found.")
    return {
        "module": module,
        "module_name": words[0]["module_name"],
        "word_count": len(words),
        "words": words,
    }


@app.get("/api/review")
def get_review_words():
    ensure_vocab_loaded()
    return {
        "word_count": len(vocab_store),
        "words": [public_word(item) for item in vocab_store],
    }


@app.get("/api/quiz")
def get_quiz(module: int | None = None, count: int = 14):
    ensure_vocab_loaded()
    if module is None:
        candidates = vocab_store[:]
    else:
        candidates = [
            item for item in vocab_store
            if int(item.get("module", -1)) == module
        ]

    try:
        quiz = build_quiz(candidates, all_words=vocab_store, count=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    quiz["module"] = module
    return quiz


@app.post("/api/check-answer")
def check_answer_api(request: AnswerRequest):
    result = check_quiz_answer(request.question, request.user_answer)
    if result.get("error"):
        return result

    word = find_vocab_for_question(request.question)
    review, source = generate_answer_review(word, result)
    result["review"] = review
    result["review_source"] = source
    return result

@app.post("/search")
def search_vocab(request: SearchRequest):
    results = retrieve_vocab(request.query, request.k)

    return {
        "query": request.query,
        "results": results
    }


@app.post("/api/rag-context")
def rag_context(request: RagContextRequest):
    chunks = retrieve_course_context(request.query, request.k)
    return {
        "query": request.query,
        "chunks": chunks,
    }

@app.post("/lesson")
def generate_lesson(request: LessonRequest):
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Invalid session_id")

    retrieved_vocab = retrieve_vocab(request.topic, request.k)
    course_chunks = retrieve_course_context(request.topic, 3)

    context = "\n".join(
        f"- {item['korean']} = {item['english']} ({item['module_name']})"
        for item in retrieved_vocab
    )
    course_context = "\n\n".join(
        f"[{chunk['source']} / {chunk['id']}]\n{chunk['text']}"
        for chunk in course_chunks
    )

    prompt = f"""
You are CoreKorean, a beginner Korean vocabulary tutor.

Use ONLY the vocabulary entries provided in the context.
Do not add Korean words that are not in the context.

Create a beginner-friendly lesson for this topic:
{request.topic}

Context:
{context}

Retrieved course material:
{course_context}

Your response must include:

1. Learning Section
- List each Korean word
- Give the English meaning
- Give a simple explanation

2. Practice Section
- Create a 14-question multiple-choice quiz
- Each question should ask for the English meaning of a Korean word
- Include choices A, B, C, and D

3. Answer Key
- Give the correct answer for each question
"""

    try:
        client = get_genai_client()
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt
        )

        sessions[request.session_id].append({
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "retrieved_course_context": course_chunks,
            "lesson": response.text
        })

        return {
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "retrieved_course_context": course_chunks,
            "lesson": response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
