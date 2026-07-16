import os
from typing import Any, List

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, get_buffer_string, trim_messages

from src.config.config import MAX_CHAT_TOKENS, chat_model
from src.database.exceptions import SessionAccessError
from src.schema.models import Session, SessionMetaData

MESSAGE_MAP = {
    "Human": HumanMessage,
    "AI": AIMessage,
}


def _get_encoding():
    try:
        return tiktoken.encoding_for_model(chat_model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens(messages: list[BaseMessage] | BaseMessage) -> int:
    if isinstance(messages, BaseMessage):
        messages = [messages]
    text = get_buffer_string(messages)
    return len(_get_encoding().encode(text))


async def get_sessions_from_db(db, user_id: str) -> List[SessionMetaData]:
    async with db.acquire() as connection:
        sessions = await connection.fetch(
            """
                SELECT session_id, title
                FROM sessions
                WHERE user_id = $1
                ORDER BY updated_at DESC, created_at DESC
            """,
            user_id,
        )

    return [
        SessionMetaData(
            session_id=row["session_id"],
            title=(row["title"] or row["session_id"]),
        )
        for row in sessions
    ]


async def get_session_context_from_db(session_id: str, user_id: str, db) -> dict[str, Any]:
    async with db.acquire() as connection:
        session_row = await connection.fetchrow(
            """
                SELECT title
                FROM sessions
                WHERE session_id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )
        if session_row is None:
            foreign_exists = await connection.fetchval(
                """
                    SELECT 1
                    FROM sessions
                    WHERE session_id = $1
                """,
                session_id,
            )
            return {
                "exists": False,
                "foreign": bool(foreign_exists),
                "title": None,
                "history": [],
            }

        rows = await connection.fetch(
            """
                SELECT id, role, content
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at ASC, id ASC
            """,
            session_id,
        )

    history = [
        MESSAGE_MAP[row["role"]](content=row["content"])
        for row in rows
        if row["role"] in MESSAGE_MAP
    ]
    return {
        "exists": True,
        "foreign": False,
        "title": session_row["title"],
        "history": history,
    }


async def get_session_history_from_db(
    session_id: str, user_id: str, db
) -> dict[str, Any] | None:
    context = await get_session_context_from_db(session_id=session_id, user_id=user_id, db=db)
    if context["foreign"] or not context["exists"]:
        return None

    async with db.acquire() as connection:
        rows = await connection.fetch(
            """
                SELECT id, role, content
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at ASC, id ASC
            """,
            session_id,
        )

    history = [
        Session(sequence_no=row["id"], role=row["role"], content=row["content"])
        for row in rows
    ]
    return {"history": history, "title": context["title"]}


async def get_session_history(session_id: str, user_id: str, db):
    context = await get_session_context_from_db(session_id=session_id, user_id=user_id, db=db)
    if context["foreign"]:
        raise SessionAccessError("Session does not belong to the current user")

    history = context["history"]
    if not history:
        return []

    return trim_messages(
        history,
        max_tokens=MAX_CHAT_TOKENS,
        token_counter=_count_tokens,
        strategy="last",
        allow_partial=True,
    )
