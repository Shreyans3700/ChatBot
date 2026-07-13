from pydantic import BaseModel, Field
from typing import List


class RequestModel(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    user_query: str = Field(min_length=1, max_length=10_000)


class ResponseModel(BaseModel):
    session_id: str
    user_query: str
    answer: str
    model_used: str
    tokens_used: int
    latency_time: float


class SessionHistoryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


class Session(BaseModel):
    sequence_no: int
    role: str
    content: str


class SessionHistoryResponse(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    history: List[Session] = []
