from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_IMAGE_PIXELS_HARD_LIMIT = 16_777_216


class Settings(BaseSettings):
    PROJECT_NAME: str = "vddai-backend"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@postgres:5432/vision_ai"
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_SECRET_KEY: str = "change-this-secret"
    JWT_EXPIRE_MINUTES: int = 60

    MAX_IMAGE_SIZE_MB: int = Field(default=5, ge=1)
    MAX_IMAGE_PIXELS: int = Field(
        default=MAX_IMAGE_PIXELS_HARD_LIMIT,
        ge=1,
        le=MAX_IMAGE_PIXELS_HARD_LIMIT,
    )
    IMAGE_STORAGE_BACKEND: Literal["local"] = "local"
    IMAGE_STORAGE_ROOT: str = "uploads"

    PREDICTION_RATE_LIMIT_REQUESTS: int = Field(default=10, ge=1)
    PREDICTION_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    PREDICTION_USER_OUTSTANDING_LIMIT: int = Field(default=5, ge=1)
    PREDICTION_GLOBAL_OUTSTANDING_LIMIT: int = Field(default=50, ge=1)
    PREDICTION_CAPACITY_RETRY_AFTER_SECONDS: int = Field(default=5, ge=1)

    MODEL_IMAGE_WIDTH: int = 224
    MODEL_IMAGE_HEIGHT: int = 224
    MODEL_DEVICE: str = "cpu"
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    WORKER_MAX_ATTEMPTS: int = Field(default=3, ge=1)
    WORKER_RETRY_DELAY_SECONDS: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
    )
    WORKER_ATTEMPT_LEASE_SECONDS: float = Field(
        default=300.0,
        gt=0,
        allow_inf_nan=False,
    )
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

    @model_validator(mode="after")
    def validate_prediction_capacity_limits(self) -> "Settings":
        if (
            self.PREDICTION_GLOBAL_OUTSTANDING_LIMIT
            < self.PREDICTION_USER_OUTSTANDING_LIMIT
        ):
            raise ValueError(
                "Global prediction capacity cannot be below the per-user limit."
            )
        return self


settings = Settings()
