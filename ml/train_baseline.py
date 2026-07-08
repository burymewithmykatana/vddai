import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score,f1_score
from sklearn.model_selection import train_test_split


ARTIFACTS_DIR = Path("artifacts")
MODEL_PATH = ARTIFACTS_DIR / "model.joblib"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"


def train_baseline_model() -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    
    dataset = load_breast_cancer(as_frame=True)
    
    X = dataset.data
    y = dataset.target
    
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    
    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        max_depth=5,
    )
    
    model.fit(X_train, y_train)
    
    predictions = model.predict(X_test)
    
    metrics = {
        "accuracy": accuracy_score(y_test, predictions),
        "f1_score": f1_score(y_test, predictions),
        "model_type": "RandomForestClassifier",
        "dataset": "sklearn breast cancer dataset",
        "target_classes": {
            "0": "malignant",
            "1": "benign",
        },
    }
    
    joblib.dump(model, MODEL_PATH)
    
    with open(METRICS_PATH, "w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=4)
        
    print("Model trained successfully")
    print(f"Model saved to: {MODEL_PATH}")
    print(f"Metrics saved to: {METRICS_PATH}")
    print(metrics)
    

if __name__ == "__main__":
    train_baseline_model()