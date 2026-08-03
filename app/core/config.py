from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "vddai-backend"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@postgres:5432/vision_ai"
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_SECRET_KEY: str = "change-this-secret"
    JWT_EXPIRE_MINUTES: int = 60

    CONFIDENCE_THRESHOLD: float = 0.75
    MAX_IMAGE_SIZE_MB: int = 5

    MODEL_IMAGE_WIDTH: int = 224
    MODEL_IMAGE_HEIGHT: int = 224
    MODEL_DEVICE: str = "cpu"
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    FEATURE_BANK_DIR: str = "artifacts/feature_banks/mvtec_ad_tile_train_resnet18"
    MODEL_PACKAGE_MANIFEST_PATH: str = (
        "artifacts/evaluations/baseline_q95_20260729/run_manifest.json"
    )
    # Accepted only so older local .env files remain readable; serving ignores it.
    THRESHOLD_ARTIFACT_PATH: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
