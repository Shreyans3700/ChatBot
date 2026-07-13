# EndToEndChatBot

EndToEndChatBot is a FastAPI-based chatbot application that uses LangChain and Groq to generate responses while keeping chat history in PostgreSQL for each session.

## Features

- FastAPI backend with chat and streaming endpoints
- Persistent session and message history in PostgreSQL
- LangChain prompt chaining with a Groq LLM
- Configurable recent-message context window via environment variable
- Docker support for containerized deployment

## Tech Stack

- Python 3.11
- FastAPI
- LangChain
- LangChain Groq
- asyncpg
- PostgreSQL
- Docker

## Prerequisites

Before running the project, make sure you have:

- Python 3.11+
- PostgreSQL running and reachable
- A Groq API key

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=qwen/qwen3.6-27b
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=postgres
DB_POOL_SIZE=10
MAX_CHAT_HISTORY_MESSAGES=20
```

The app expects a PostgreSQL database named `LangchainDB`.

## Local Development

1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Start the application

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

- http://localhost:8000/

## API Endpoints

### Health check

```bash
curl http://localhost:8000/
```

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-session",
    "user_query": "Hello!"
  }'
```

### Stream chat

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-session",
    "user_query": "Tell me a short joke"
  }'
```

### Get session history

```bash
curl "http://localhost:8000/getSessionHistory?session_id=demo-session"
```

## Docker

Build and run the app with Docker:

```bash
docker build -t chatbot .
docker run --env-file .env -p 8000:8000 chatbot
```

## Notes

- The app stores all message history in PostgreSQL.
- The context sent to the model is trimmed to the most recent configured number of messages to avoid excessive prompt size.
- If you want to change the context window size, update `MAX_CHAT_HISTORY_MESSAGES` in your `.env` file.
