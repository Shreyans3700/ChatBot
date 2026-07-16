from typing import Any, AsyncGenerator
import json
import time

from langchain_core.messages import AIMessage

from src.database.fetch_data import get_session_history
from src.database.update_data import update_session_history


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "content"):
        value = getattr(value, "content")
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text", item)))
            elif hasattr(item, "content"):
                parts.append(str(getattr(item, "content")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(value)


async def stream_answer(
    session_id: str, user_query: str, db, chain, title_chain
) -> AsyncGenerator[str, None]:
    history = await get_session_history(
        session_id=session_id,
        db=db,
    )
    title = None
    if len(history) == 0:
        print("This is a new chat")
        title = await title_chain.ainvoke({"query": user_query})
        title = str(title.content)
        print("Title for the chat:", title)

    final_answer = ""
    saw_nonempty_chunk = False

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

        if event_type == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            chunk_text = _extract_text(chunk)

            if chunk_text:
                saw_nonempty_chunk = True
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

            if not final_answer and output is not None:
                final_answer = _extract_text(output)

    final_answer = final_answer.strip()

    if final_answer and not saw_nonempty_chunk:
        yield (
            "event: token\n"
            f"data: {json.dumps({'token': final_answer})}\n\n"
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

    await update_session_history(
        session_id=session_id,
        user_message=user_query,
        ai_message=final_ai_message,
        db=db,
        title=title,
    )

    payload = {
        "model": model_name,
        "tokens": total_tokens,
        "latency": latency,
    }

    yield ("event: done\n" f"data: {json.dumps(payload)}\n\n")