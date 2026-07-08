from pydantic import BaseModel, ConfigDict


class PredictionInput(BaseModel):
    mean_radius: float
    mean_texture: float
    mean_perimeter: float
    mean_area: float
    mean_smoothness: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mean_radius": 14.2,
                "mean_texture": 20.5,
                "mean_perimeter": 90.2,
                "mean_area": 600.1,
                "mean_smoothness": 0.1,
            }
        }
    )


class PredictionOutput(BaseModel):
    prediction: int
    prediction_label: str