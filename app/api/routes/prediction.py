from fastapi import APIRouter

from app.schemas.prediction import PredictionInput, PredictionOutput
from app.services.model_service import model_service


router = APIRouter(tags=["prediction"])


@router.post("/predict", response_model=PredictionOutput)
def predict(payload: PredictionInput) -> PredictionOutput:
    result = model_service.predict(payload.model_dump())
    return PredictionOutput(**result)
