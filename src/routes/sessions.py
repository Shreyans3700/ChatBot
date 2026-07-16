import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.auth import get_current_user
from src.database.fetch_data import get_session_history_from_db, get_sessions_from_db
from src.routes.dependencies import get_db
from src.schema.models import SessionHistoryResponse, SessionMetaData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


@router.get("/getSessionHistory")
async def get_session_history(
    session_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
) -> SessionHistoryResponse:
    try:
        session_history = await get_session_history_from_db(
            session_id=session_id,
            user_id=current_user.id,
            db=db,
        )
        if session_history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        return SessionHistoryResponse(
            session_id=session_id,
            title=session_history["title"] or session_id,
            history=session_history["history"],
            status_code=status.HTTP_200_OK,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Get session history failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch session history",
        ) from error


@router.get("/getSessionMetaData", response_model=List[SessionMetaData])
async def get_sessions(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
) -> List[SessionMetaData]:
    try:
        return await get_sessions_from_db(db=db, user_id=current_user.id)
    except Exception as error:
        logger.exception("failed to fetch session metadata")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch sessions metadata",
        ) from error
