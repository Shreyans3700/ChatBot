from src.db import get_session_history, update_session_history
from typing import AsyncGenerator
import json
import time
from langchain_core.messages import AIMessage


async def get_answer(session_id: str, user_query: str, db, chain) -> dict:
    history = await get_session_history(session_id=session_id, db=db)
    response = await chain.ainvoke({"chat_history": history, "query": user_query})

    metadata = response.response_metadata
    token_usage = metadata.get("token_usage") or {}
    final_response = str(response.content)
    model_used = str(metadata.get("model_name", "unknown"))
    total_token_used = int(token_usage.get("total_tokens", 0))
    time_taken = float(token_usage.get("total_time", 0.0))

    save_status = await update_session_history(
        session_id=session_id,
        user_message=user_query,
        ai_message=response,
        db=db,
    )
    if not save_status:
        raise RuntimeError("Failed to persist conversation history")

    return {
        "answer": final_response,
        "model_used": model_used,
        "tokens": total_token_used,
        "latency_time": time_taken,
    }


async def stream_answer(
    session_id: str,
    user_query: str,
    db,
    chain,
) -> AsyncGenerator[str, None]:

    # -------------------------
    # Load Previous History
    # -------------------------
    history = await get_session_history(
        session_id=session_id,
        db=db,
    )

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

    # -------------------------
    # Stream Events
    # -------------------------

    async for event in chain.astream_events(
        {
            "chat_history": history,
            "query": user_query,
        },
        version="v2",
    ):

        event_type = event["event"]

        # -------------------------
        # Token Streaming
        # -------------------------

        if event_type == "on_chat_model_stream":

            chunk = event["data"]["chunk"]

            if chunk.content:
                final_answer += chunk.content

                yield (
                    f"event: token\n"
                    f"data: {json.dumps({'token': chunk.content})}\n\n"
                )

        # -------------------------
        # Model Finished
        # -------------------------

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

    # -------------------------
    # Save History
    # -------------------------

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
    )

    # -------------------------
    # Final Event
    # -------------------------

    payload = {
        "model": model_name,
        "tokens": total_tokens,
        "latency": latency,
    }

    yield ("event: done\n" f"data: {json.dumps(payload)}\n\n")
