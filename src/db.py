import json
import logging
from typing import Any, List
from src.models import SessionMetaData
from langchain_core.messages import AIMessage, HumanMessage, trim_messages

from src.config import MAX_CHAT_TOKENS
from src.models import Session

logger = logging.getLogger(__name__)

MESSAGE_MAP = {
    "Human": HumanMessage,
    "AI": AIMessage,
}


def _serialize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if text_value:
                    parts.append(str(text_value))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        try:
            return json.dumps(content, ensure_ascii=False)
        except TypeError:
            return str(content)
    return str(content)


async def get_sessions_from_db(db) -> List[SessionMetaData]:
    async with db.acquire() as connection:
        sessions = await connection.fetch("""
                select session_id, title
                from sessions
            """)

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


async def get_session_history(session_id: str, db, llm):
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
        token_counter=llm,
        strategy="last",
        allow_partial=True,
    )


async def update_session_history(
    session_id: str, user_message: str, ai_message: AIMessage, db, title
) -> bool:
    user_content = _serialize_message_content(user_message)
    ai_content = _serialize_message_content(
        ai_message.content if hasattr(ai_message, "content") else ai_message
    )
    try:
        async with db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO sessions (session_id, title)
                    VALUES ($1, $2)
                    ON CONFLICT (session_id) DO NOTHING
                    """,
                    session_id,
                    title,
                )
                await connection.execute(
                    """
                    INSERT INTO messages (session_id, role, content)
                    VALUES ($1, 'Human', $2)
                    """,
                    session_id,
                    user_content,
                )
                await connection.execute(
                    """
                    INSERT INTO messages (session_id, role, content)
                    VALUES ($1, 'AI', $2)
                    """,
                    session_id,
                    ai_content,
                )
                await connection.execute(
                    """
                    UPDATE sessions
                    SET updated_at = NOW()
                    WHERE session_id = $1
                    """,
                    session_id,
                )
        return True
    except Exception as exc:
        logger.exception(
            "Failed to persist conversation history for session %s", session_id
        )
        return False
