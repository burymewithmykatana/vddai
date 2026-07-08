# VDDAI Backend

Visual Defect Detection AI backend.

This project is a production-oriented machine learning backend built with FastAPI. The long-term goal is to serve an AI-powered visual defect detection system with a clean API, database layer, model-serving layer, and deployable infrastructure.

## Current Status

The project currently includes:

- FastAPI application structure
- Health check routes
- SQLAlchemy database setup
- PostgreSQL support through Docker Compose
- Baseline ML training script
- Saved model metrics
- Prediction API route
- Service layer for loading and using the model
- Automated API tests

## Tech Stack

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy
- PostgreSQL
- Docker Compose
- scikit-learn
- pandas
- joblib
- pytest

## Project Structure

```text
app/
├── api/
│   └── routes/
│       ├── health.py
│       └── prediction.py
├── core/
│   └── config.py
├── db/
│   ├── init_db.py
│   └── session.py
├── schemas/
│   ├── __init__.py
│   └── prediction.py
├── services/
│   └── model_service.py
└── main.py

ml/
└── train_baseline.py

artifacts/
├── metrics.json
└── .gitkeep

tests/
└── test_prediction_api.py