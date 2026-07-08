from pydantic import BaseModel, ConfigDict


class PredictionCreate(BaseModel):
    user_id: int
    image_path: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "image_path": "uploads/test_image_001.jpg",
            }
        }
    )


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