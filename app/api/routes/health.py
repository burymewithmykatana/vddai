from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.services.model_package_loader import resolve_production_model_selection
from app.services.promoted_model_resolver import PromotedModelResolutionError

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/db")
def database_health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/health/model")
def model_health_check():
    """Expose the selected version without registry paths or private metadata."""
    try:
        selection = resolve_production_model_selection()
    except PromotedModelResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="production_model_unavailable",
        ) from exc
    return {
        "status": "selected",
        "model_version": selection.model_version,
        "package_id": selection.package_id,
    }
