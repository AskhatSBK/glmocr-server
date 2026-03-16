from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    LOG_LEVEL: str = "INFO"
    ENABLE_DOCS: bool = True

    # --- Auth ---
    # Comma-separated list of valid API keys. Empty = auth disabled (dev only).
    API_KEYS: str = ""

    @property
    def api_keys_set(self) -> set[str]:
        if not self.API_KEYS:
            return set()
        return {k.strip() for k in self.API_KEYS.split(",") if k.strip()}

    # --- Rate limiting ---
    RATE_LIMIT_REQUESTS: int = 60   # requests per window
    RATE_LIMIT_WINDOW: int = 60     # seconds

    # --- File upload ---
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # --- RunPod serverless backend ---
    RUNPOD_ENDPOINT_URL: str = ""   # https://api.runpod.ai/v2/<endpoint_id>
    RUNPOD_API_KEY: str = ""
    RUNPOD_TIMEOUT: int = 300       # seconds to wait for job completion

    # --- Output ---
    OUTPUT_FORMAT: str = "both"   # json | markdown | both

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
