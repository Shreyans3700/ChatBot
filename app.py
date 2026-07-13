import logging

import uvicorn
from fastapi import FastAPI, HTTPException
from src.config import set_environment
from src.models import (
    RequestModel,
    ResponseModel,
    SessionHistoryRequest,
    SessionHistoryResponse,
)
from fastapi.responses import StreamingResponse
from src.llm import get_answer, stream_answer
from src.db import get_session_history_from_db

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EndToEndChatBot",
    description="Complete Chatbot with persistent history",
    version="0.0.1",
    lifespan=set_environment,
)


@app.get("/")
async def index():
    return {"service": "EndToEndChatBot", "status": "ok"}


@app.post("/chat", response_model=ResponseModel)
async def chat_with_bot(request: RequestModel) -> ResponseModel:
    try:
        response = await get_answer(
            session_id=request.session_id,
            user_query=request.user_query,
            chain=app.state.chain,
            db=app.state.db,
        )
    except Exception as error:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=502, detail="Unable to generate a response"
        ) from error

    return ResponseModel(
        session_id=request.session_id,
        user_query=request.user_query,
        answer=response["answer"],
        model_used=response["model_used"],
        tokens_used=response["tokens"],
        latency_time=response["latency_time"],
    )


@app.get("/getSessionHistory")
async def get_session_history(request: SessionHistoryRequest) -> SessionHistoryResponse:
    session_id = request.session_id
    history = await get_session_history_from_db(session_id=session_id, db=app.state.db)

    return SessionHistoryResponse(session_id=session_id, history=history)


@app.post("/chat/stream")
async def stream_chat(request: RequestModel) -> StreamingResponse:
    try:
        return StreamingResponse(
            stream_answer(
                session_id=request.session_id,
                user_query=request.user_query,
                chain=app.state.chain,
                db=app.state.db,
            ),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.exception("Stream request failed.")
        raise HTTPException(
            status_code=502, detail="Unable to generate a response"
        ) from e


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=8000)
