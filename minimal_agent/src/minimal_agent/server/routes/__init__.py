"""API route table — everything the App mounts under /api."""

from fastapi import APIRouter

from .agents import router as agents_router
from .chat import router as chat_router
from .config import router as config_router
from .observability import router as observability_router
from .sessions import router as sessions_router
from .tools import router as tools_router

api_router = APIRouter()
api_router.include_router(config_router)
api_router.include_router(agents_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(tools_router)
api_router.include_router(observability_router)


@api_router.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
