import json
import logging
from typing import Any
from langchain_core.messages import AIMessage, HumanMessage

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
                if title is not None:
                    await connection.execute(
                        """
                        INSERT INTO sessions (session_id, title)
                        VALUES ($1, $2)
                        ON CONFLICT (session_id) DO UPDATE
                        SET title = EXCLUDED.title,
                            updated_at = NOW()
                        """,
                        session_id,
                        title,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE sessions
                        SET updated_at = NOW()
                        WHERE session_id = $1
                        """,
                        session_id,
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
