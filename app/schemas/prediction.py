from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PredictionQueuedResponse(BaseModel):
    prediction_id: int
    status: str
    message: str


class PredictionRead(BaseModel):
    id: int
    user_id: int
    image_path: str
    image_format: str
    image_width: int
    image_height: int
    status: str
    predicted_label: str | None
    confidence: float | None
    anomaly_score: float | None
    threshold: float | None
    model_version: str | None
    model_lineage: dict[str, object] | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
