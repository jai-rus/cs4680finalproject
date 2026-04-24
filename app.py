from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
import os
import json
import uuid

load_dotenv()

app = FastAPI()

# Ignore for now
# app.mount("/static", StaticFiles(directory="static"), name="static")

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

sessions = {}
vocab_store = []
module_store = {}

class LessonRequest(BaseModel):
    session_id: str
    topic: str = Field(min_length=1)
    k: int = 10

class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = 10

@app.get("/")
def root():
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
        with open("data/small_vocab.json", "r", encoding="utf-8") as f:
            vocab_store = json.load(f)

        module_store = {}

        for item in vocab_store:
            module = item["module"]

            if module not in module_store:
                module_store[module] = []

            module_store[module].append(item)

        return {
            "message": "Vocabulary ingested successfully",
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


def retrieve_vocab(topic: str, k: int = 10):

    if not vocab_store:
        raise HTTPException(
            status_code=400,
            detail="Vocabulary not ingested yet. Call /ingest-vocab first."
        )

    topic_lower = topic.lower()

    module_keywords = {
        "greetings": "Greetings & Basics",
        "basic": "Greetings & Basics",
        "basics": "Greetings & Basics",
        "hello": "Greetings & Basics",

        "number": "Numbers",
        "numbers": "Numbers",
        "count": "Numbers",

        "food": "Food & Restaurant",
        "restaurant": "Food & Restaurant",
        "drink": "Food & Restaurant",
        "eating": "Food & Restaurant",

        "family": "Family & People",
        "people": "Family & People",
        "person": "Family & People",

        "place": "Places",
        "places": "Places",
        "location": "Places",
        "school": "Places",
        "home": "Places",

        "day": "Days & Time",
        "days": "Days & Time",
        "time": "Days & Time",
        "week": "Days & Time",

        "verb": "Daily Verbs",
        "verbs": "Daily Verbs",
        "daily": "Daily Verbs",
        "actions": "Daily Verbs",

        "weather": "Weather & Seasons",
        "season": "Weather & Seasons",
        "seasons": "Weather & Seasons",

        "shopping": "Shopping & Money",
        "money": "Shopping & Money",
        "store": "Shopping & Money",

        "feeling": "Feelings & States",
        "feelings": "Feelings & States",
        "emotion": "Feelings & States",
        "states": "Feelings & States"
    }

    selected_module = None

    for keyword, module in module_keywords.items():
        if keyword in topic_lower:
            selected_module = module
            break

    if selected_module and selected_module in module_store:
        return module_store[selected_module][:k]

    # fallback: search in module names, Korean words, and English meanings
    matches = []

    for item in vocab_store:
        searchable_text = f"{item['module']} {item['korean']} {item['english']}".lower()

        if topic_lower in searchable_text:
            matches.append(item)

    if matches:
        return matches[:k]

    # final fallback: return first k words
    return vocab_store[:k]

@app.post("/search")
def search_vocab(request: SearchRequest):
    results = retrieve_vocab(request.query, request.k)

    return {
        "query": request.query,
        "results": results
    }

@app.post("/lesson")
def generate_lesson(request: LessonRequest):
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Invalid session_id")

    retrieved_vocab = retrieve_vocab(request.topic, request.k)

    context = "\n".join(
        f"- {item['korean']} = {item['english']} ({item['module']})"
        for item in retrieved_vocab
    )

    prompt = f"""
You are CoreKorean, a beginner Korean vocabulary tutor.

Use ONLY the vocabulary entries provided in the context.
Do not add Korean words that are not in the context.

Create a beginner-friendly lesson for this topic:
{request.topic}

Context:
{context}

Your response must include:

1. Learning Section
- List each Korean word
- Give the English meaning
- Give a simple explanation

2. Practice Section
- Create a 10-question multiple-choice quiz
- Each question should ask for the English meaning of a Korean word
- Include choices A, B, C, and D

3. Answer Key
- Give the correct answer for each question
"""

    try:
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt
        )

        sessions[request.session_id].append({
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "lesson": response.text
        })

        return {
            "topic": request.topic,
            "retrieved_vocab": retrieved_vocab,
            "lesson": response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))