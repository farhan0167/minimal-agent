"""Application settings loaded from environment variables / .env.

Usage:

    from config import settings

    llm = LLM(model=settings.LLM_MODEL, backend=settings.LLM_BACKEND)

Values come from (in priority order): process env vars, then a .env file in
the working directory. See .env.example for the full list.
"""

from enum import StrEnum
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Backend(StrEnum):
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    LOCALHOST = "localhost"


_BACKEND_FALLBACK_KEYS: dict[Backend, str] = {
    Backend.OPENAI: "OPENAI_API_KEY",
    Backend.OPENROUTER: "OPENROUTER_API_KEY",
    Backend.ANTHROPIC: "ANTHROPIC_API_KEY",
    Backend.LOCALHOST: "OPENAI_API_KEY",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Backend selection -------------------------------------------------
    LLM_BACKEND: Backend = Field(default=Backend.OPENAI)

    # --- Backend credentials ------------------------------------------------
    # Preferred: set LLM_BACKEND_API_KEY to the key for whatever backend
    # is active.  Falls back to the conventional env var for the active
    # backend (OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY) so
    # existing .env files keep working.
    LLM_BACKEND_API_KEY: Optional[str] = Field(default=None)

    # Conventional per-provider keys — used as fallback only.
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENROUTER_API_KEY: Optional[str] = Field(default=None)
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)

    # Override the base URL for the backend. Required for "localhost"
    # (e.g. http://localhost:8000/v1 for vLLM, llama.cpp, LM Studio, Ollama).
    # For other backends this overrides the provider's default URL.
    LLM_BACKEND_BASE_URL: Optional[str] = Field(default=None)

    # Optional: site URL and app name shown on OpenRouter's leaderboards.
    # Ignored by other backends.
    LLM_BACKEND_SITE_URL: Optional[str] = Field(default=None)
    LLM_BACKEND_APP_NAME: Optional[str] = Field(default=None)

    # --- Client overrides --------------------------------------------------
    OPENAI_TIMEOUT: Optional[float] = Field(default=None)
    OPENAI_MAX_RETRIES: Optional[int] = Field(default=None)

    # --- Model selection ---------------------------------------------------
    LLM_MODEL: str = Field(default="gpt-4o-mini")

    # --- Session persistence -----------------------------------------------
    SESSIONS_DIR: str = Field(default=".minimal_agent/sessions")

    @model_validator(mode="after")
    def _resolve_api_key(self) -> "Settings":
        """If LLM_BACKEND_API_KEY isn't set, fall back to the
        conventional env var for the active backend."""
        if self.LLM_BACKEND_API_KEY is None:
            fallback_field = _BACKEND_FALLBACK_KEYS[self.LLM_BACKEND]
            fallback_value = getattr(self, fallback_field, None)
            if fallback_value is not None:
                self.LLM_BACKEND_API_KEY = fallback_value
        if self.LLM_BACKEND == Backend.LOCALHOST and not self.LLM_BACKEND_BASE_URL:
            raise ValueError(
                "LLM_BACKEND_BASE_URL is required when LLM_BACKEND='localhost'"
            )
        return self


settings = Settings()
