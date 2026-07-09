from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key:  str   = "REPLACE_ME"
    gemini_model:    str   = "gemini-1.5-flash"

    firebase_credentials_path: str  = "./firebase-credentials.json"
    firebase_project_id:       str  = "REPLACE_ME"

    app_env:   str = "development"
    log_level: str = "INFO"

    confidence_threshold_low:  float = 0.50
    confidence_threshold_high: float = 0.80

    max_audio_size_mb: int = 10
    max_image_size_mb: int = 5

    # Phase 2 — clustering
    # Cosine similarity threshold for joining an existing cluster (0.0–1.0)
    # 0.72 catches paraphrases without false-merging unrelated topics
    cluster_similarity_threshold: float = 0.72

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()