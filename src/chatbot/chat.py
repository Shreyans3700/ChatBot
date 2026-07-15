from src.database.fetch_data import get_session_history
from src.database.update_data import update_session_history


async def get_answer(session_id: str, user_query: str, db, chain, title_chain) -> dict:
    history = await get_session_history(session_id=session_id, db=db)
    title = None
    if len(history) == 0:
        print("This is a new chat")
        title = await title_chain.ainvoke({"query": user_query})
        title = str(title.content)
        print("Title for the chat:", title)
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
        title=title,
    )
    if not save_status:
        raise RuntimeError("Failed to persist conversation history")

    return {
        "answer": final_response,
        "model_used": model_used,
        "tokens": total_token_used,
        "latency_time": time_taken,
    }
