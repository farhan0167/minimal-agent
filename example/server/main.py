"""FastAPI server entrypoint for minimal-agent."""

import os

import uvicorn
from fastapi import FastAPI

from routes.chat import router as chat_router
from routes.sessions import router as sessions_router

app = FastAPI(
    title="minimal-agent",
    description="HTTP server for the minimal-agent framework",
    version="0.1.0",
)

app.include_router(sessions_router)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
