import pytest
import torch
from torch import Tensor, nn

from ml.feature_extractor import (
    FeatureExtractionError,
    FeatureExtractorConfig,
    IMAGENET_MEAN,
    RESNET18_FEATURE_DIM,
    ResNet18FeatureExtractor,
)


class TinyBackbone(nn.Module):
    def __init__(
        self,
        feature_dim: int = 4,
    ) -> None:
        super().__init__()
        self.feature_dim = feature_dim
        self.projection = nn.Linear(
            3,
            feature_dim,
            bias=False,
        )
        with torch.no_grad():
            weights = torch.zeros(
                (feature_dim, 3),
                dtype=torch.float32,
            )
            base_weights = torch.tensor(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [0.5, 0.25, 0.125],
                ],
                dtype=torch.float32,
            )
            rows = min(
                feature_dim,
                base_weights.shape[0],
            )
            weights[:rows] = base_weights[:rows]
            self.projection.weight.copy_(weights)

    def forward(self, images: Tensor) -> Tensor:
        pooled = images.mean(
            dim=(2, 3),
        )
        return self.projection(pooled)


def create_extractor(
    feature_dim: int = 4,
) -> ResNet18FeatureExtractor:
    return ResNet18FeatureExtractor(
        config=FeatureExtractorConfig(device="cpu"),
        backbone=TinyBackbone(feature_dim=feature_dim),
        feature_dim=feature_dim,
    )


def test_feature_extractor_outputs_one_vector_per_image() -> None:
    extractor = create_extractor()
    images = torch.full(
        (2, 3, 8, 8),
        fill_value=0.5,
        dtype=torch.float32,
    )

    features = extractor.extract(images)

    assert features.shape == (2, 4)
    assert features.dtype == torch.float32
    assert features.is_contiguous()


def test_feature_values_are_finite() -> None:
    extractor = create_extractor()
    images = torch.rand(
        (3, 3, 8, 8),
        dtype=torch.float32,
    )

    features = extractor.extract(images)

    assert torch.isfinite(features).all()


def test_cpu_device_is_explicit_and_supported() -> None:
    extractor = create_extractor()
    images = torch.rand(
        (2, 3, 8, 8),
        dtype=torch.float32,
    )

    features = extractor.extract(images)

    assert extractor.device.type == "cpu"
    assert features.device.type == "cpu"


def test_identical_inputs_produce_stable_outputs() -> None:
    extractor = create_extractor()
    images = torch.full(
        (2, 3, 8, 8),
        fill_value=0.25,
        dtype=torch.float32,
    )

    first_features = extractor.extract(images)
    second_features = extractor.extract(images)

    assert torch.equal(
        first_features,
        second_features,
    )


def test_extraction_does_not_track_gradients() -> None:
    extractor = create_extractor()
    images = torch.rand(
        (2, 3, 8, 8),
        dtype=torch.float32,
        requires_grad=True,
    )

    features = extractor.extract(images)

    assert features.requires_grad is False
    assert all(
        parameter.requires_grad is False
        for parameter in extractor.parameters()
    )


def test_model_remains_in_evaluation_mode() -> None:
    extractor = create_extractor()
    extractor.train()

    images = torch.rand(
        (2, 3, 8, 8),
        dtype=torch.float32,
    )

    extractor.extract(images)

    assert extractor.training is False
    assert extractor.backbone.training is False


def test_invalid_input_dtype_is_rejected() -> None:
    extractor = create_extractor()
    images = torch.zeros(
        (2, 3, 8, 8),
        dtype=torch.float64,
    )

    with pytest.raises(
        FeatureExtractionError,
        match="torch.float32",
    ):
        extractor.extract(images)


@pytest.mark.parametrize(
    "shape",
    [
        (3, 8, 8),
        (2, 1, 8, 8),
        (2, 3, 8),
    ],
)
def test_invalid_input_shape_is_rejected(
    shape: tuple[int, ...],
) -> None:
    extractor = create_extractor()
    images = torch.zeros(
        shape,
        dtype=torch.float32,
    )

    with pytest.raises(
        FeatureExtractionError,
        match=r"\(N, 3, H, W\)",
    ):
        extractor.extract(images)


def test_input_range_is_validated_before_normalization() -> None:
    extractor = create_extractor()
    images = torch.full(
        (2, 3, 8, 8),
        fill_value=1.1,
        dtype=torch.float32,
    )

    with pytest.raises(
        FeatureExtractionError,
        match=r"range \[0, 1\]",
    ):
        extractor.extract(images)


def test_imagenet_normalization_lives_inside_adapter() -> None:
    extractor = create_extractor()
    images = torch.empty(
        (1, 3, 8, 8),
        dtype=torch.float32,
    )

    for channel, mean in enumerate(IMAGENET_MEAN):
        images[:, channel].fill_(mean)

    normalized = extractor._normalize(images)

    assert torch.allclose(
        normalized,
        torch.zeros_like(normalized),
        atol=1e-6,
    )


def test_default_feature_dimension_documents_resnet18_output() -> None:
    extractor = create_extractor(feature_dim=RESNET18_FEATURE_DIM)

    assert extractor.feature_dim == 512
