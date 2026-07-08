"""
config.py — Single source of truth for all settings.
Loaded once at startup; everything imports from here.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini (Google AI Studio — free tier)
    gemini_api_key:  str   = "REPLACE_ME"
    gemini_model:    str   = "gemini-1.5-flash"

    # Firebase
    firebase_credentials_path: str  = "./firebase-credentials.json"
    firebase_project_id:       str  = "REPLACE_ME"

    # App
    app_env:   str = "development"
    log_level: str = "INFO"

    # Confidence thresholds
    confidence_threshold_low:  float = 0.50
    confidence_threshold_high: float = 0.80

    # File limits
    max_audio_size_mb: int = 10
    max_image_size_mb: int = 5

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
