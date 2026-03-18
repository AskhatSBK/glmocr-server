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
    ENABLE_AUTH: bool = False   # set true to enforce API key checks
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
    # Comma-separated: .pdf,.jpg,.jpeg,.png,.doc,.docx
    ALLOWED_EXTENSIONS: str = ".pdf,.jpg,.jpeg,.png,.doc,.docx"

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [e.strip() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    # --- GLM-OCR backend ---
    OCR_MODE: str = "selfhosted"          # selfhosted | maas
    OCR_API_HOST: str = "192.168.90.10"
    OCR_API_PORT: int = 8888
    OCR_API_SCHEME: str = "http"
    OCR_API_KEY: str = ""                 # required for maas mode
    OCR_MODEL: str = "glm-ocr"   # model name served by vLLM
    OCR_CONNECT_TIMEOUT: int = 30
    OCR_REQUEST_TIMEOUT: int = 300
    OCR_ENABLE_LAYOUT: bool = False
    # --- Output ---
    OUTPUT_FORMAT: str = "both"   # json | markdown | both

    # --- CORS ---
    # Comma-separated origins, or * for all
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # --- Async job queue (optional Celery) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_TASK_QUEUE: bool = True


settings = Settings()
