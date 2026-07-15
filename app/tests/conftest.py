import os

# Pytest loads conftest.py before importing test modules.
# This prevents application settings and the SQLAlchemy engine
# from being initialized with Docker-only environment values.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_vddai.db"
