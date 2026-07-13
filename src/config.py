import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq

MAX_CHAT_HISTORY_MESSAGES = int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "20"))

from src.prompts import system_prompt

load_dotenv()

chat_model = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")


def required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


@asynccontextmanager
async def set_environment(app: FastAPI):
    app.state.llm = ChatGroq(
        model=chat_model,
        api_key=required_setting("GROQ_API_KEY"),
        reasoning_format="hidden",
        temperature=0.6,
        max_retries=3,
    )
    app.state.qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{query}"),
        ]
    )
    app.state.chain = app.state.qa_prompt | app.state.llm
    app.state.db = await asyncpg.create_pool(
        host=required_setting("DB_HOST"),
        port=int("5432"),
        database="LangchainDB",
        user=required_setting("DB_USER"),
        password=required_setting("DB_PASSWORD"),
        min_size=1,
        max_size=int(os.getenv("DB_POOL_SIZE", "10")),
    )

    try:
        async with app.state.db.acquire() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('Human', 'AI')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS messages_session_id_id_idx
                    ON messages (session_id, id);
                """)
        yield
    finally:
        await app.state.db.close()
