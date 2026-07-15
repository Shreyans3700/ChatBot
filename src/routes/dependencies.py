from typing import Any

from fastapi import Request
from langchain_core.runnables import Runnable
import asyncpg


def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db


def get_chain(request: Request) -> Runnable[Any, Any]:
    return request.app.state.chain


def get_title_chain(request: Request) -> Runnable[Any, Any]:
    return request.app.state.title_chain
