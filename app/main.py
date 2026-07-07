from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Visual Defect Detection AI backend made for upcoming awesome projects, summer 2026.",
    lifespan=lifespan,
)


@app.get("/", tags=["root"])
def root():
    return {
        "message": "visual defect AI backend is running.",
        "docs": "/docs",
    }


app.include_router(health.router)
