# CoreKorean

CoreKorean is a Korean vocabulary learning web app built with:

- **FastAPI** for the web server
- **MCP** for tool-based vocabulary and quiz logic
- **Gemini** for lesson generation and quiz-answer explanations
- **YouTube integration** for pronunciation and usage video links

 ## Contributors

- Alison Ching
- Hyewon Kang
- Jairus Legion
- Cynthia Nguyen

## Features

- Browse Korean vocabulary by module
- View Korean word, romanization, English meaning, and example sentence
- Practice writing with the tracing canvas
- Watch or search pronunciation videos on YouTube
- Take module quizzes and final review quizzes
- Get richer **MCQ-only quiz explanations** from Gemini through the MCP tool
- Retrieve PDF course context for lesson generation with a simple RAG flow

---

## Project structure

Your project should look like this:

```text
project/
  app.py
  server.py
  vocab_bank.json
  .env
  Korean_Vocabulary_140_Final.pdf      # optional, for /ingest-docs and lesson RAG
  static/
    index.html
    app.js
    styles.css
```

### Important

- `app.py` expects the frontend files inside a folder named `static/`
- `server.py` is the MCP server process launched by `app.py`
- `vocab_bank.json` is required
- `Korean_Vocabulary_140_Final.pdf` is optional

---

## What each file does

### `app.py`
Runs the FastAPI app.

It is responsible for:
- starting the MCP client session
- launching `server.py`
- serving the frontend
- exposing API routes like:
  - `/api/modules`
  - `/api/modules/{module}/words`
  - `/api/quiz`
  - `/api/explain-answer`
  - `/lesson`
  - `/api/rag-context`

### `server.py`
Runs the MCP server.

It provides tools such as:
- `get_vocab_session`
- `get_module_vocab`
- `generate_quiz`
- `check_answer`
- `explain_quiz_answer`
- `get_youtube_recommendation`
- `enrich_youtube_links`

### `static/app.js`
Frontend logic for:
- loading modules
- showing vocabulary words
- rendering YouTube videos
- starting quizzes
- sending MCQ answers to `/api/explain-answer`

### `static/index.html`
Frontend page layout.

### `static/styles.css`
Frontend styling.

---

## Requirements

- Python 3.10+
- A virtual environment is recommended
- Internet access for Gemini and YouTube API features

Install these Python packages:

```bash
pip install fastapi uvicorn python-dotenv pydantic google-genai mcp fastmcp pypdf google-generativeai
```

Depending on your environment, you may also already have some of them installed.

---

## Environment variables

Create a `.env` file in the project root.

Use this:

```env
GOOGLE_API_KEY=your_real_api_key
GEMINI_API_KEY=your_real_api_key
GEMINI_MODEL=models/gemini-2.5-flash
YOUTUBE_API_KEY=your_youtube_api_key_optional
```

### Notes

#### `GOOGLE_API_KEY`
Used by `app.py` for lesson generation.

#### `GEMINI_API_KEY`
Used by `server.py` for the `explain_quiz_answer` MCP tool.

#### `GEMINI_MODEL`
Recommended value:

```env
GEMINI_MODEL=models/gemini-2.5-flash
```

#### `YOUTUBE_API_KEY`
Optional.

- If set, YouTube tools can return verified video links.
- If not set, the app falls back to YouTube search URLs.

---

## How to run the app

### 1. Activate your virtual environment

Example:

```bash
source .venv/bin/activate
```

### 2. Start the FastAPI server

```bash
uvicorn app:app --reload
```

This will:
- start FastAPI
- launch the MCP server from `server.py`
- open the MCP client session automatically

### 3. Open the website

Go to:

```text
http://127.0.0.1:8000/
```

If everything is set up correctly, you should see the CoreKorean website.

---
