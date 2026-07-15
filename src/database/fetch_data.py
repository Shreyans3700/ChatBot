import os
from typing import Any, List

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, get_buffer_string, trim_messages

from src.config.config import MAX_CHAT_TOKENS, chat_model
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


async def get_sessions_from_db(db) -> List[SessionMetaData]:
    async with db.acquire() as connection:
        sessions = await connection.fetch(
            """
                select session_id, title
                from sessions
            """
        )

        sessions = [
            SessionMetaData(session_id=row["session_id"], title=row["title"])
            for row in sessions
        ]

    return sessions


async def get_session_history_from_db(session_id: str, db) -> dict:
    async with db.acquire() as connection:
        rows = await connection.fetch(
            """
                select id, role, content
                from messages
                where session_id=$1
                order by created_at ASC, id ASC
            """,
            session_id,
        )
        title_row = await connection.fetchrow(
            """
                select title
                from sessions
                where session_id=$1
            """,
            session_id,
        )
        title = title_row["title"] if title_row else None
        history = [
            Session(sequence_no=row["id"], role=row["role"], content=row["content"])
            for row in rows
        ]
        return {"history": history, "title": title}


async def get_session_history(session_id: str, db):
    async with db.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT role, content
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

    if not history:
        return []

    return trim_messages(
        history,
        max_tokens=MAX_CHAT_TOKENS,
        token_counter=_count_tokens,
        strategy="last",
        allow_partial=True,
    )
