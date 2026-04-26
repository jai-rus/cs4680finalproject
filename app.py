from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
import asyncio
import json
import os
import uuid
import re
from pathlib import Path

load_dotenv()

# ── MCP session (lifespan-managed) ────────────────────────────────────────────

mcp_session: ClientSession | None = None
_stdio_cm = None
_session_cm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_session, _stdio_cm, _session_cm

    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=os.environ.copy(),
    )

    _stdio_cm = stdio_client(server_params)
    read, write = await _stdio_cm.__aenter__()

    _session_cm = ClientSession(read, write)
    mcp_session = await _session_cm.__aenter__()
    await mcp_session.initialize()

    yield

    await _session_cm.__aexit__(None, None, None)
    await _stdio_cm.__aexit__(None, None, None)


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)

STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

sessions: dict = {}
vocab_store: list = []
module_store: dict = {}
doc_chunks: list = []


# ── Pydantic models ───────────────────────────────────────────────────────────

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


# ── MCP helper ────────────────────────────────────────────────────────────────

async def call_tool(name: str, arguments: dict) -> any:
    """Call an MCP tool and return the parsed JSON result."""
    if mcp_session is None:
        raise HTTPException(status_code=503, detail="MCP session not ready.")
    result = await mcp_session.call_tool(name, arguments=arguments)
    raw = result.content[0].text
    return json.loads(raw)


# ── Ingest helpers (kept in app.py per spec) ──────────────────────────────────

def get_vocab_path() -> Path:
    return Path("vocab_bank.json")


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
    return "\n".join(page.extract_text() or "" for page in reader.pages)


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


def query_terms(query: str):
    return [
        term for term in re.findall(r"[\w가-힣]+", query.lower())
        if len(term) > 1
    ]


def retrieve_course_context(query: str, k: int = 3):
    if not doc_chunks:
        return []
    terms = query_terms(query)
    if not terms:
        return doc_chunks[:k]
    scored = []
    for chunk in doc_chunks:
        text = chunk["text"].lower()
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]


def get_genai_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not set.")
    return genai.Client(api_key=api_key)


# ── Routes ────────────────────────────────────────────────────────────────────

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
            "modules_loaded": list(module_store.keys()),
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
            module_store.setdefault(module, []).append(item)

        return {
            "message": "Vocabulary ingested successfully",
            "source_file": str(vocab_path),
            "words_loaded": len(vocab_store),
            "modules_loaded": list(module_store.keys()),
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Could not find file.")
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
        pdf_paths = [Path("Korean_Vocabulary_140_Final.pdf")]
        loaded = []
        for path in pdf_paths:
            if not path.exists():
                continue
            text = extract_pdf_text(path)
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
            detail="pypdf is not installed. Run pip install -r requirements.txt.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── API routes delegating to MCP tools ───────────────────────────────────────

@app.get("/api/modules")
async def list_modules():
    """Aggregate all modules by calling get_module_vocab for each known module."""
    # We use vocab_store (ingested locally) to know which module numbers exist,
    # then let the MCP tool be the source of truth for word data.
    if not vocab_store:
        raise HTTPException(status_code=400, detail="Call /ingest-vocab first.")

    module_numbers = sorted(
        {int(item["module"]) for item in vocab_store if item.get("module") is not None}
    )

    modules = []
    for mod_num in module_numbers:
        data = await call_tool("get_module_vocab", {"module": mod_num, "level": "beginner"})
        if "error" not in data:
            modules.append({
                "module": data["module"],
                "module_name": data["module_name"],
                "word_count": data["word_count"],
            })

    return {"modules": modules}


@app.get("/api/modules/{module}/words")
async def get_module_words(module: int):
    data = await call_tool("get_module_vocab", {"module": module, "level": "beginner"})
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return {
        "module": data["module"],
        "module_name": data["module_name"],
        "word_count": data["word_count"],
        "words": data["words"],
    }


@app.get("/api/review")
async def get_review_words():
    data = await call_tool("get_vocab_session", {"level": "beginner", "topic": "any"})
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return {
        "word_count": data["word_count"],
        "words": data["words"],
    }


@app.get("/api/quiz")
async def get_quiz(module: int | None = None, count: int = 14):
    # Step 1: get vocab words via MCP
    if module is not None:
        vocab_data = await call_tool(
            "get_module_vocab", {"module": module, "level": "beginner"}
        )
    else:
        vocab_data = await call_tool(
            "get_vocab_session", {"level": "beginner", "topic": "any"}
        )

    if "error" in vocab_data:
        raise HTTPException(status_code=400, detail=vocab_data["error"])

    words = vocab_data["words"]
    if len(words) < 4:
        raise HTTPException(status_code=400, detail="Need at least 4 words for a quiz.")

    # Step 2: generate quiz via MCP
    quiz_data = await call_tool(
        "generate_quiz",
        {
            "vocab_list": words,
            "question_types": ["multiple_choice"],
        },
    )

    if "error" in quiz_data:
        raise HTTPException(status_code=500, detail=quiz_data["error"])

    # Trim to requested count
    questions = quiz_data["questions"][:count]

    return {
        "module": module,
        "question_count": len(questions),
        "questions": questions,
    }


@app.post("/search")
async def search_vocab(request: SearchRequest):
    data = await call_tool(
        "get_vocab_session",
        {"level": "beginner", "topic": request.query},
    )
    if "error" in data:
        # Graceful fallback: return empty results rather than 500
        return {"query": request.query, "results": []}
    return {"query": request.query, "results": data["words"]}


@app.post("/api/rag-context")
def rag_context(request: RagContextRequest):
    chunks = retrieve_course_context(request.query, request.k)
    return {"query": request.query, "chunks": chunks}

@app.post("/api/explain-answer")
async def explain_answer(payload: dict):
    question = payload.get("question")
    user_answer = payload.get("user_answer", "")
    vocab_word = payload.get("vocab_word")

    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    data = await call_tool(
        "explain_quiz_answer",
        {
            "question": question,
            "user_answer": user_answer,
            "vocab_word": vocab_word,
        },
    )

    if "error" in data and "question_id" not in data:
        raise HTTPException(status_code=400, detail=data["error"])

    return data

@app.post("/lesson")
async def generate_lesson(request: LessonRequest):
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Invalid session_id")

    # Fetch vocab via MCP
    vocab_data = await call_tool(
        "get_vocab_session",
        {"level": "beginner", "topic": request.topic},
    )
    if "error" in vocab_data:
        raise HTTPException(status_code=500, detail=vocab_data["error"])

    retrieved_vocab = vocab_data["words"]
    course_chunks = retrieve_course_context(request.topic, 3)

    context = "\n".join(
        f"- {item['korean']} = {item['english']} ({item.get('module_name', '')})"
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
            contents=prompt,
        )

        sessions[request.session_id].append({
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "retrieved_course_context": course_chunks,
            "lesson": response.text,
        })

        return {
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "retrieved_course_context": course_chunks,
            "lesson": response.text,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))