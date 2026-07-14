from pydantic import BaseModel, ConfigDict


class PredictionQueuedResponse(BaseModel):
    prediction_id: int
    status: str
    message: str


class PredictionRead(BaseModel):
    id: int
    user_id: int
    image_path: str
    status: str
    predicted_label: str | None
    confidence: float | None
    threshold: float
    model_version: str
    latency_ms: int | None
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)
