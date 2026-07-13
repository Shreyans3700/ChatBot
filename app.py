import logging
from typing import List
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi import Depends
from src.config import set_environment
from src.models import (
    RequestModel,
    ResponseModel,
    SessionHistoryRequest,
    SessionHistoryResponse,
    SessionMetaData,
)
from fastapi.responses import StreamingResponse
from src.llm import get_answer, stream_answer
from src.db import get_session_history_from_db, get_sessions_from_db
from src.auth import verify_api_key

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


@app.post("/chat", response_model=ResponseModel, dependencies=[Depends(verify_api_key)])
async def chat_with_bot(request: RequestModel) -> ResponseModel:
    try:
        response = await get_answer(
            session_id=request.session_id,
            user_query=request.user_query,
            chain=app.state.chain,
            title_chain=app.state.title_chain,
            db=app.state.db,
        )
    except Exception as error:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to generate a response",
        ) from error

    return ResponseModel(
        session_id=request.session_id,
        user_query=request.user_query,
        answer=response["answer"],
        model_used=response["model_used"],
        tokens_used=response["tokens"],
        latency_time=response["latency_time"],
        status_code=status.HTTP_200_OK,
    )


@app.get("/getSessionHistory", dependencies=[Depends(verify_api_key)])
async def get_session_history(request: SessionHistoryRequest) -> SessionHistoryResponse:
    try:
        session_id = request.session_id
        session_history = await get_session_history_from_db(
            session_id=session_id, db=app.state.db
        )

        title = session_history["title"]
        history = session_history["history"]

        return SessionHistoryResponse(
            session_id=session_id,
            title=title,
            history=history,
            status_code=status.HTTP_200_OK,
        )
    except Exception as error:
        logger.exception("Get session history failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch session history",
        ) from error


@app.get("/getSessionMetaData", dependencies=[Depends(verify_api_key)])
async def get_sessions() -> List[SessionMetaData]:
    try:
        sessions = await get_sessions_from_db(db=app.state.db)
        return sessions
    except Exception as error:
        logger.exception("failed to fetch session metadata")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch sessions metadata",
        ) from error


@app.post("/chat/stream", dependencies=[Depends(verify_api_key)])
async def stream_chat(request: RequestModel) -> StreamingResponse:
    try:
        return StreamingResponse(
            stream_answer(
                session_id=request.session_id,
                user_query=request.user_query,
                chain=app.state.chain,
                db=app.state.db,
                title_chain=app.state.title_chain
            ),
            media_type="text/event-stream",
            status_code=status.HTTP_200_OK,
        )
    except Exception as error:
        logger.exception("Stream request failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to generate a response",
        ) from error


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=8000)
