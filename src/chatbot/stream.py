import json
import logging
import time
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage

from src.database.exceptions import SessionAccessError
from src.database.fetch_data import get_session_context_from_db
from src.database.update_data import update_session_history

logger = logging.getLogger(__name__)


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "content", None)
                if text:
                    parts.append(str(text))
        return "\n".join(part for part in parts if part)
    if hasattr(value, "content"):
        return _extract_text(value.content)
    if isinstance(value, dict):
        for key in ("content", "output", "text"):
            text = value.get(key)
            if text:
                return _extract_text(text)
    return str(value)


def _preview(text: str, limit: int = 200) -> str:
    clean = text.replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


async def stream_answer(
    session_id: str,
    user_id: str,
    user_query: str,
    db,
    chain,
    title_chain,
    session_context: dict | None = None,
) -> AsyncGenerator[str, None]:
    if session_context is None:
        session_context = await get_session_context_from_db(
            session_id=session_id,
            user_id=user_id,
            db=db,
        )

    if session_context["foreign"]:
        raise SessionAccessError("Session does not belong to the current user")

    history = session_context["history"]
    logger.info(
        "Starting streamed chat: session=%s user=%s exists=%s history_len=%s query_len=%s",
        session_id,
        user_id,
        session_context["exists"],
        len(history),
        len(user_query),
    )

    title = None
    if not session_context["exists"]:
        logger.info("New session detected: session=%s", session_id)
        title = await title_chain.ainvoke({"query": user_query})
        title = str(title.content).strip() or "New Chat"
        logger.info("Generated title for session=%s title=%r", session_id, title)

    final_answer = ""
    model_name = "unknown"
    total_tokens = 0
    latency = 0.0
    start_time = time.perf_counter()

    def _get_token_usage(source: dict | object | None) -> dict:
        if source is None:
            return {}
        if isinstance(source, dict):
            return source
        if hasattr(source, "usage_metadata") and source.usage_metadata:
            return dict(source.usage_metadata)
        if hasattr(source, "response_metadata") and source.response_metadata:
            return dict(source.response_metadata.get("token_usage", {}))
        return {}

    def _get_model_metadata(source: dict | object | None) -> dict:
        if source is None:
            return {}
        if isinstance(source, dict):
            return source
        if hasattr(source, "response_metadata") and source.response_metadata:
            return dict(source.response_metadata)
        return {}

    async for event in chain.astream_events(
        {
            "chat_history": history,
            "query": user_query,
        },
        version="v2",
    ):
        event_type = event["event"]
        if event_type in {"on_chat_model_stream", "on_chat_model_end", "on_llm_end", "on_chain_end"}:
            logger.debug(
                "Stream event received: session=%s event=%s keys=%s",
                session_id,
                event_type,
                sorted((event.get("data") or {}).keys()),
            )

        if event_type == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            chunk_text = _extract_text(getattr(chunk, "content", None))
            logger.debug(
                "Token chunk: session=%s chunk_len=%s chunk_text=%r",
                session_id,
                len(chunk_text),
                _preview(chunk_text),
            )
            if chunk_text:
                final_answer += chunk_text
                yield (
                    f"event: token\n"
                    f"data: {json.dumps({'token': chunk_text})}\n\n"
                )

        elif event_type in {"on_chat_model_end", "on_llm_end", "on_chain_end"}:
            output = event["data"].get("output")
            event_metadata = event.get("metadata") or {}
            usage_metadata = _get_token_usage(output)
            if not usage_metadata:
                usage_metadata = _get_token_usage(event_metadata)
            if not usage_metadata and isinstance(output, dict):
                usage_metadata = _get_token_usage(output.get("llm_output"))

            if not final_answer:
                final_answer = _extract_text(output).strip()

            model_metadata = _get_model_metadata(output)
            model_metadata = {**event_metadata, **model_metadata}

            total_tokens = usage_metadata.get("total_tokens")
            if total_tokens is None:
                total_tokens = int(
                    usage_metadata.get("output_tokens", 0)
                    + usage_metadata.get("input_tokens", 0)
                )
            latency = usage_metadata.get("total_time")
            if latency is None:
                latency = usage_metadata.get("completion_time")
            if latency is None:
                latency = time.perf_counter() - start_time
            latency = float(latency)
            model_name = str(model_metadata.get("model_name", "unknown"))
            logger.debug(
                "Stream end event: session=%s model=%s tokens=%s latency=%s output_type=%s final_answer_len=%s final_answer_preview=%r",
                session_id,
                model_name,
                total_tokens,
                latency,
                type(output).__name__ if output is not None else None,
                len(final_answer),
                _preview(final_answer),
            )

    final_answer = final_answer.strip()
    if not final_answer:
        logger.warning(
            "Empty streamed answer before persistence: session=%s model=%s tokens=%s",
            session_id,
            model_name,
            total_tokens,
        )

    logger.info(
        "Persisting streamed answer: session=%s answer_len=%s model=%s tokens=%s latency=%s preview=%r",
        session_id,
        len(final_answer),
        model_name,
        total_tokens,
        latency,
        _preview(final_answer),
    )

    final_ai_message = AIMessage(
        content=final_answer,
        response_metadata={
            "token_usage": {
                "total_tokens": total_tokens,
                "total_time": latency,
            },
            "model_name": model_name,
        },
    )

    try:
        await update_session_history(
            session_id=session_id,
            user_id=user_id,
            user_message=user_query,
            ai_message=final_ai_message,
            db=db,
            title=title,
        )
        logger.info("Persisted streamed answer: session=%s", session_id)
    except Exception:
        logger.exception("Failed to persist streamed chat history for session %s", session_id)

    payload = {
        "model": model_name,
        "tokens": total_tokens,
        "latency": latency,
    }

    yield ("event: done\n" f"data: {json.dumps(payload)}\n\n")
