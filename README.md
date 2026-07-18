# nexus-rag

EndToEndChatBot is a FastAPI-based chatbot application that uses LangChain and OpenAI to generate responses while keeping chat history in PostgreSQL for each authenticated user. It includes a full **RAG (Retrieval-Augmented Generation) pipeline** — upload documents to a session, and the chatbot will ground its answers using the most relevant chunks from those documents.

## Features

- FastAPI backend with chat and streaming endpoints
- JWT-based signup and login
- Persistent user, session, and message history in PostgreSQL
- LangChain prompt chaining with an OpenAI chat model
- Configurable recent-message context window via environment variable
- **RAG pipeline**: upload PDF, DOCX, TXT, MD, or CSV files per session
- **Milvus vector store** for fast semantic search (with automatic Postgres fallback)
- **Dual-write resilience**: chunk text stored in Postgres `document_chunks` so Milvus can be rebuilt at any time
- Background document ingestion (upload returns instantly, embedding happens async)
- Docker support for containerized deployment

## Tech Stack

- Python 3.11
- FastAPI
- LangChain
- LangChain OpenAI
- asyncpg
- PostgreSQL
- Milvus (vector store)
- Streamlit
- Docker

## Prerequisites

Before running the project, make sure you have:

- Python 3.11+
- PostgreSQL running and reachable
- **Milvus Standalone** running (see Docker Compose section below)
- An OpenAI API key for the backend model
- A strong JWT secret for signing user tokens

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
OPENAI_API_KEY=your_openai_api_key
JWT_SECRET=your_long_random_jwt_secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_HASH_ITERATIONS=210000
LLM_MODEL=gpt-4o-mini
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=LangchainDB
PG_USER=postgres
PG_PASSWORD=postgres
DB_POOL_SIZE=10
MAX_CHAT_TOKENS=2500

# Milvus (RAG vector store)
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=doc_chunks
MILVUS_TOP_K=5
```

## Local Development

1. **Start Milvus** (requires Docker):

```bash
docker compose up -d
```

This starts etcd, MinIO, and Milvus Standalone on port `19530`.

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the backend:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

5. Start the Streamlit frontend:

```bash
streamlit run frontend.py
```

The API will be available at `http://localhost:8000` and the frontend at `http://localhost:8501`.

## Authentication

- `POST /auth/signup` — creates a user and returns an access token.
- `POST /auth/login` — verifies credentials and returns an access token.
- Authenticated requests must include `Authorization: Bearer <token>`.

## RAG Usage

1. Log in from the sidebar.
2. In the chat input, attach one or more files (PDF, DOCX, TXT, MD, CSV).
3. The frontend shows per-file ingestion status (⏳ processing → ✅ ready).
4. Once ready, ask questions — answers will be grounded in your document content.
5. Documents are scoped to the current session. New sessions start fresh.

### Resilience

Chunk text is stored in PostgreSQL `document_chunks` as well as in Milvus. If Milvus is unavailable or its data is lost, the retriever automatically falls back to Postgres, re-embeds the chunks, restores them to Milvus, and continues serving queries without downtime.

## API Endpoints

### Auth

```bash
# Sign up
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "strong-password"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "strong-password"}'
```

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id": "demo-session", "user_query": "Hello!"}'

# Streaming
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id": "demo-session", "user_query": "Tell me a short joke"}'
```

### Documents

```bash
# Upload files (session_id is a required form field)
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "session_id=demo-session" \
  -F "files=@report.pdf" \
  -F "files=@notes.txt"

# List documents for a session
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/documents?session_id=demo-session"

# Delete a document
curl -X DELETE http://localhost:8000/documents/{document_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Session History

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/getSessionHistory?session_id=demo-session"
```

## Docker

Start the full stack (Milvus + etcd + MinIO) with:

```bash
docker compose up -d
```

To also containerize the FastAPI app, build and run:

```bash
docker build -t chatbot .
docker run --env-file .env -p 8000:8000 chatbot
```

## Notes

- The context sent to the model is trimmed to the most recent configured number of messages. Update `MAX_CHAT_HISTORY_MESSAGES` in `.env` to change the window.
- `MILVUS_TOP_K` controls how many document chunks are retrieved per query (default 5).
- The streaming endpoint falls back to the final end-of-stream answer when a model emits empty chunks.
- Document ingestion is asynchronous — the upload endpoint returns `202 Accepted` immediately. Poll `GET /documents?session_id=...` to watch status change from `processing` to `ready`.
