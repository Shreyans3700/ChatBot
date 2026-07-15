import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.auth import verify_api_key
from src.database.fetch_data import get_session_history_from_db, get_sessions_from_db
from src.routes.dependencies import get_db
from src.schema.models import SessionHistoryResponse, SessionMetaData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


@router.get("/getSessionHistory", dependencies=[Depends(verify_api_key)])
async def get_session_history(
    session_id: str = Query(...),
    db=Depends(get_db),
) -> SessionHistoryResponse:
    try:
        session_history = await get_session_history_from_db(session_id=session_id, db=db)

        return SessionHistoryResponse(
            session_id=session_id,
            title=session_history["title"] or session_id,
            history=session_history["history"],
            status_code=status.HTTP_200_OK,
        )
    except Exception as error:
        logger.exception("Get session history failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch session history",
        ) from error


@router.get("/getSessionMetaData", dependencies=[Depends(verify_api_key)])
async def get_sessions(db=Depends(get_db)) -> List[SessionMetaData]:
    try:
        return await get_sessions_from_db(db=db)
    except Exception as error:
        logger.exception("failed to fetch session metadata")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch sessions metadata",
        ) from error
