from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "vddai-backend"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@postgres:5432/vision_ai"
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_SECRET_KEY: str = "change-this-secret"
    JWT_EXPIRE_MINUTES: int = 60

    MAX_IMAGE_SIZE_MB: int = 5

    MODEL_IMAGE_WIDTH: int = 224
    MODEL_IMAGE_HEIGHT: int = 224
    MODEL_DEVICE: str = "cpu"
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    MODEL_REGISTRY_PATH: str = "artifacts/registry/model_registry.sqlite3"
    MODEL_ARTIFACT_ROOT: str = "."
    # Accepted only so older local .env files remain readable; serving ignores them.
    FEATURE_BANK_DIR: str | None = None
    MODEL_PACKAGE_MANIFEST_PATH: str | None = None
    # Accepted only so older local .env files remain readable; serving ignores it.
    THRESHOLD_ARTIFACT_PATH: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
