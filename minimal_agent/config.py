"""Application settings loaded from environment variables / .env.

Usage:

    from config import settings

    llm = LLM(model=settings.LLM_MODEL, backend=settings.LLM_BACKEND)

Values come from (in priority order): process env vars, then a .env file in
the working directory. See .env.example for the full list.
"""

from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Backend = Literal["openai", "openrouter", "anthropic"]

_BACKEND_FALLBACK_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Backend selection -------------------------------------------------
    LLM_BACKEND: Backend = Field(default="openai")

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

    # Optional: site URL and app name shown on OpenRouter's leaderboards.
    # Ignored by other backends.
    LLM_BACKEND_SITE_URL: Optional[str] = Field(default=None)
    LLM_BACKEND_APP_NAME: Optional[str] = Field(default=None)

    # --- Client overrides --------------------------------------------------
    OPENAI_TIMEOUT: Optional[float] = Field(default=None)
    OPENAI_MAX_RETRIES: Optional[int] = Field(default=None)

    # --- Model selection ---------------------------------------------------
    LLM_MODEL: str = Field(default="gpt-4o-mini")

    @model_validator(mode="after")
    def _resolve_api_key(self) -> "Settings":
        """If LLM_BACKEND_API_KEY isn't set, fall back to the
        conventional env var for the active backend."""
        if self.LLM_BACKEND_API_KEY is None:
            fallback_field = _BACKEND_FALLBACK_KEYS[self.LLM_BACKEND]
            fallback_value = getattr(self, fallback_field, None)
            if fallback_value is not None:
                self.LLM_BACKEND_API_KEY = fallback_value
        return self


settings = Settings()
