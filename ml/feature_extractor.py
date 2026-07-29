"""Frozen pretrained image feature extraction for anomaly baselines.

Default architecture:
- Network: torchvision ResNet-18 with ``ResNet18_Weights.DEFAULT``.
- Selected output: global-average-pooled penultimate representation, before
  the final classification layer.
- Output dimension: 512 features per image.
- Expected input: ``(N, 3, H, W)`` ``torch.float32`` tensors in ``[0, 1]``.
  ImageNet mean/std normalization is applied inside this adapter.
- Freeze policy: all backbone parameters are frozen and the module is kept in
  evaluation mode because Week 4 uses ResNet-18 as a fixed representation
  baseline, not as a trainable classifier.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn
from torchvision.models import ResNet18_Weights, resnet18


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
RESNET18_EXTRACTOR_NAME = "torchvision.resnet18"
RESNET18_WEIGHTS_IDENTIFIER = ResNet18_Weights.DEFAULT.name
RESNET18_FEATURE_LAYER = "avgpool"
RESNET18_FEATURE_DIM = 512


class FeatureExtractionError(ValueError):
    """Raised when an image batch cannot be converted to features."""


@dataclass(frozen=True)
class FeatureExtractorConfig:
    """Configuration for the frozen feature extractor."""

    device: str | torch.device = "cpu"


def resolve_device(device: str | torch.device) -> torch.device:
    """Resolve a requested device and fail clearly when CUDA is unavailable."""
    resolved = torch.device(device)

    if resolved.type == "cuda" and not torch.cuda.is_available():
        raise FeatureExtractionError(
            "CUDA was requested but is not available."
        )

    return resolved


def build_resnet18_feature_backbone(
    weights: ResNet18_Weights | None = ResNet18_Weights.DEFAULT,
) -> nn.Module:
    """Create a ResNet-18 trunk that emits pooled image-level features."""
    model = resnet18(weights=weights)
    return nn.Sequential(
        *list(model.children())[:-1],
    )


class ResNet18FeatureExtractor(nn.Module):
    """Extract one frozen ResNet-18 feature vector per input image."""

    def __init__(
        self,
        config: FeatureExtractorConfig | None = None,
        backbone: nn.Module | None = None,
        feature_dim: int = RESNET18_FEATURE_DIM,
    ) -> None:
        super().__init__()

        self.config = config or FeatureExtractorConfig()
        self.device = resolve_device(self.config.device)
        self.feature_dim = feature_dim

        self.backbone = (
            backbone
            if backbone is not None
            else build_resnet18_feature_backbone()
        )

        self.register_buffer(
            "normalization_mean",
            torch.tensor(
                IMAGENET_MEAN,
                dtype=torch.float32,
            ).view(1, 3, 1, 1),
        )
        self.register_buffer(
            "normalization_std",
            torch.tensor(
                IMAGENET_STD,
                dtype=torch.float32,
            ).view(1, 3, 1, 1),
        )

        self.to(self.device)
        self._freeze()
        self.eval()

    def _freeze(self) -> None:
        for parameter in self.parameters():
            parameter.requires_grad_(False)

    def _validate_images(self, images: Tensor) -> None:
        if images.dtype != torch.float32:
            raise FeatureExtractionError(
                "Image batch must use torch.float32."
            )

        if images.ndim != 4 or images.shape[1] != 3:
            raise FeatureExtractionError(
                "Image batch must have shape (N, 3, H, W)."
            )

        if images.shape[0] <= 0:
            raise FeatureExtractionError(
                "Image batch must contain at least one image."
            )

        if not torch.isfinite(images).all():
            raise FeatureExtractionError(
                "Image batch must contain only finite values."
            )

        if images.min().item() < 0.0 or images.max().item() > 1.0:
            raise FeatureExtractionError(
                "Image batch values must be in the range [0, 1]."
            )

    def _normalize(self, images: Tensor) -> Tensor:
        mean = self.normalization_mean.to(
            device=images.device,
            dtype=images.dtype,
        )
        std = self.normalization_std.to(
            device=images.device,
            dtype=images.dtype,
        )
        return (images - mean) / std

    def extract(self, images: Tensor) -> Tensor:
        """Return ``(N, feature_dim)`` image-level feature vectors."""
        self.eval()
        self._validate_images(images)

        with torch.inference_mode():
            batch = images.to(
                self.device,
                non_blocking=False,
            )
            normalized = self._normalize(batch)
            features = self.backbone(normalized)

            if features.ndim > 2:
                features = torch.flatten(
                    features,
                    start_dim=1,
                )

            if features.ndim != 2:
                raise FeatureExtractionError(
                    "Backbone must return one feature vector per image."
                )

            if features.shape[0] != images.shape[0]:
                raise FeatureExtractionError(
                    "Feature batch size must match image batch size."
                )

            if features.shape[1] != self.feature_dim:
                raise FeatureExtractionError(
                    "Unexpected feature dimension. "
                    f"Expected {self.feature_dim}, "
                    f"received {features.shape[1]}."
                )

            return features.contiguous()

    def forward(self, images: Tensor) -> Tensor:
        return self.extract(images)
