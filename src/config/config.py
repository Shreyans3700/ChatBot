import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq

from src.config.prompts import system_prompt, title_prompt

MAX_CHAT_TOKENS = int(os.getenv("MAX_CHAT_TOKENS", "2500"))
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "210000"))

chat_model = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")


def required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


llm = ChatGroq(
    model=chat_model,
    api_key=required_setting("GROQ_API_KEY"),
    reasoning_format="hidden",
    temperature=0.6,
    max_retries=3,
)


@asynccontextmanager
async def set_environment(app: FastAPI):
    app.state.qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{query}"),
        ]
    )
    app.state.title_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", title_prompt),
            ("human", "{query}"),
        ]
    )
    app.state.chain = app.state.qa_prompt | llm
    app.state.title_chain = app.state.title_prompt | llm
    app.state.db = await asyncpg.create_pool(
        host=required_setting("PG_HOST"),
        port=int(required_setting("PG_PORT")),
        database=required_setting("PG_DATABASE"),
        user=required_setting("PG_USER"),
        password=required_setting("PG_PASSWORD"),
        min_size=1,
        max_size=int(os.getenv("DB_POOL_SIZE", "10")),
    )

    try:
        async with app.state.db.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT NOT NULL,
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
                CREATE INDEX IF NOT EXISTS sessions_user_id_idx
                    ON sessions (user_id);
                """
            )
            await connection.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id TEXT"
            )
        yield
    finally:
        await app.state.db.close()
