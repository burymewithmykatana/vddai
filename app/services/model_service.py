from pathlib import Path

import joblib
import pandas as pd


MODEL_PATH=Path("artifacts/model.joblib")


class ModelService:
    """An adapter between user input and model input
    """
    def __init__(self) -> None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}. "
                "Run `python ml/train_baseline.py` first."
            )
            
        self.model = joblib.load(MODEL_PATH)
        
    def predict(self, input_data: dict) -> dict:
        expected_features = self.model.feature_names_in_
        
        row = {feature: 0.0 for feature in expected_features}
        
        mapping = {
            "mean_radius": "mean radius",
            "mean_texture": "mean texture",
            "mean_perimeter": "mean perimeter",
            "mean_area": "mean area",
            "mean_smoothness": "mean smoothness",
        }
        
        for api_field, model_field in mapping.items():
            row[model_field] = input_data[api_field]
            
        df = pd.DataFrame([row], columns=expected_features)
        
        prediction = int(self.model.predict(df)[0])
        label = "benign" if prediction == 1 else "malignant"
        
        return {
            "prediction": prediction,
            "prediction_label": label,
        }
        
        
model_service = ModelService()