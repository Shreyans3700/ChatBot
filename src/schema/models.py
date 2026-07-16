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
    status_code: int = Field(200, ge=100, le=599)


class SessionHistoryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


class SessionMetaData(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=128)


class Session(BaseModel):
    sequence_no: int
    role: str
    content: str


class SessionHistoryResponse(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=128)
    history: List[Session] = Field(default_factory=list)
    status_code: int = Field(200, ge=100, le=599)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=254)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CurrentUser(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=254)
