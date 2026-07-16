# EndToEndChatBot

EndToEndChatBot is a FastAPI-based chatbot application that uses LangChain and Groq to generate responses while keeping chat history in PostgreSQL for each authenticated user.

## Features

- FastAPI backend with chat and streaming endpoints
- JWT-based signup and login
- Persistent user, session, and message history in PostgreSQL
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
- Streamlit
- Docker

## Prerequisites

Before running the project, make sure you have:

- Python 3.11+
- PostgreSQL running and reachable
- A Groq API key for the backend model
- A strong JWT secret for signing user tokens

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
GROQ_API_KEY=your_groq_api_key
JWT_SECRET=your_long_random_jwt_secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_HASH_ITERATIONS=210000
GROQ_MODEL=qwen/qwen3.6-27b
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=LangchainDB
PG_USER=postgres
PG_PASSWORD=postgres
DB_POOL_SIZE=10
MAX_CHAT_TOKENS=2500
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

3. Start the backend application

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

4. Start the Streamlit frontend

```bash
streamlit run frontend.py
```

The API will be available at:

- http://localhost:8000/

The frontend will run on the default Streamlit port, usually:

- http://localhost:8501/

## Authentication

The backend now uses JWT bearer tokens instead of a shared API key.

- `POST /auth/signup` creates a user and returns an access token.
- `POST /auth/login` verifies credentials and returns an access token.
- Authenticated requests must include `Authorization: Bearer <token>`.
- Sessions are scoped to the logged-in user.

## Frontend

The `frontend.py` Streamlit app provides a simple chat UI with login and signup.

- Sign up or log in from the sidebar.
- The frontend stores the JWT in session state and uses it for all backend requests.
- Sessions and history are visible only for the current user.
- Logging out clears the local token and chat state.

If you prefer to keep secrets out of your code, create a `.streamlit/secrets.toml` file with:

```toml
BACKEND_URL = "http://localhost:8000"
```

## API Endpoints

### Sign up

```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "session_id": "demo-session",
    "user_query": "Hello!"
  }'
```

### Stream chat

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "session_id": "demo-session",
    "user_query": "Tell me a short joke"
  }'
```

### Get session history

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:8000/getSessionHistory?session_id=demo-session"
```

## Docker

Build and run the app with Docker:

```bash
docker build -t chatbot .
docker run --env-file .env -p 8000:8000 chatbot
```

## Notes

- The app stores users, sessions, and message history in PostgreSQL.
- Session titles are stored on the session row and scoped to the signed-in user.
- The context sent to the model is trimmed to the most recent configured number of messages to avoid excessive prompt size.
- If you want to change the context window size, update `MAX_CHAT_HISTORY_MESSAGES` in your `.env` file.
