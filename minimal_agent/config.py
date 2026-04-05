"""Application settings loaded from environment variables / .env.

Usage:

    from config import settings

    llm = LLM(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

Values come from (in priority order): process env vars, then a .env file in
the working directory. See .env.example for the full list.
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- OpenAI / OpenAI-compatible client ---------------------------------
    # Set OPENAI_BASE_URL to point at a local server (llama.cpp, vLLM, LM
    # Studio, Ollama's /v1 endpoint, etc.). Leave unset to hit api.openai.com.
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_BASE_URL: Optional[str] = Field(default=None)
    OPENAI_TIMEOUT: Optional[float] = Field(default=None)
    OPENAI_MAX_RETRIES: Optional[int] = Field(default=None)

    # --- Model selection ---------------------------------------------------
    LLM_MODEL: str = Field(default="gpt-4o-mini")


settings = Settings()
