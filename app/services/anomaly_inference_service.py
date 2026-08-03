"""Image-level inference using one already-loaded production package."""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

import torch

from app.contracts.inference import (
    ONLINE_INPUT_CONTRACT,
    AnomalyInferenceResult,
    classify_anomaly_score,
)
from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from app.services.model_package_loader import (
    ModelPackageCompatibilityError,
    ModelPackageError,
    ProductionModelPackage,
    get_production_model_package,
)

logger = logging.getLogger(__name__)


class AnomalyInferenceService:
    """Score images without reloading or mutating the frozen package."""

    def __init__(
        self,
        *,
        package: ProductionModelPackage,
        preprocessing_service: ImagePreprocessingService = (
            image_preprocessing_service
        ),
    ) -> None:
        _, contract_height, contract_width = ONLINE_INPUT_CONTRACT.storage_tensor_shape
        if (
            preprocessing_service.target_width != contract_width
            or preprocessing_service.target_height != contract_height
        ):
            raise ModelPackageCompatibilityError(
                "Preprocessing dimensions do not match the production contract."
            )
        self.package = package
        self.preprocessing_service = preprocessing_service

    def predict(self, image_path: str | Path) -> AnomalyInferenceResult:
        started_at = time.perf_counter()
        preprocessed = self.preprocessing_service.preprocess(image_path)
        images = torch.from_numpy(preprocessed.array).unsqueeze(0)

        features = self.package.feature_extractor.extract(images)
        scores = self.package.scorer.score(features.detach().to("cpu").numpy())
        if scores.shape != (1,):
            raise ModelPackageError("Inference must produce exactly one anomaly score.")

        score = float(scores[0])
        predicted_label = classify_anomaly_score(
            score=score,
            threshold=self.package.threshold,
        )
        latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))

        logger.info(
            "anomaly_inference_completed package_id=%s label=%s score=%s "
            "threshold=%s latency_ms=%s",
            self.package.package_id,
            predicted_label,
            score,
            self.package.threshold,
            latency_ms,
        )
        return AnomalyInferenceResult(
            predicted_label=predicted_label,
            anomaly_score=score,
            threshold=self.package.threshold,
            model_version=self.package.package_id,
            model_lineage=self.package.lineage,
            latency_ms=latency_ms,
        )


@lru_cache(maxsize=1)
def get_anomaly_inference_service() -> AnomalyInferenceService:
    """Reuse one service backed by the process-cached production package."""
    return AnomalyInferenceService(package=get_production_model_package())


def reset_anomaly_inference_service_cache_for_tests() -> None:
    """Clear the service wrapper only in the test environment."""
    from app.core.config import settings

    if settings.ENVIRONMENT != "test":
        raise RuntimeError("Inference-service cache reset is restricted to tests.")
    get_anomaly_inference_service.cache_clear()
