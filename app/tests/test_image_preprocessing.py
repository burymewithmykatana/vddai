import numpy as np
import pytest
from PIL import Image

from ml.preprocessing import (
    ImagePreprocessingConfig,
    ImagePreprocessingError,
    preprocess_image,
)


@pytest.mark.parametrize(
    ("mode", "color"),
    [
        ("L", 128),
        ("RGB", (10, 20, 30)),
        ("RGBA", (10, 20, 30, 100)),
    ],
)
def test_preprocess_image_accepts_common_color_modes(
    mode: str,
    color: int | tuple[int, ...],
) -> None:
    image = Image.new(mode, (320, 180), color=color)

    result = preprocess_image(image)

    assert result.shape == (3, 224, 224)
    assert result.dtype == np.float32
    assert result.flags["C_CONTIGUOUS"]


@pytest.mark.parametrize(
    "size",
    [
        (400, 200),
        (200, 400),
        (224, 224),
        (50, 50),
    ],
)
def test_preprocess_image_returns_fixed_output_shape(
    size: tuple[int, int],
) -> None:
    image = Image.new("RGB", size, color=(100, 150, 200))

    result = preprocess_image(image)

    assert result.shape == (3, 224, 224)


def test_preprocess_image_is_deterministic() -> None:
    image = Image.new("RGB", (300, 170), color=(25, 100, 200))

    first_result = preprocess_image(image)
    second_result = preprocess_image(image)

    np.testing.assert_array_equal(first_result, second_result)


def test_preprocess_image_uses_channel_first_layout() -> None:
    image = Image.new("RGB", (224, 224), color=(255, 0, 0))

    result = preprocess_image(image)

    red_channel_mean = result[0].mean()
    green_channel_mean = result[1].mean()
    blue_channel_mean = result[2].mean()

    assert red_channel_mean > green_channel_mean
    assert red_channel_mean > blue_channel_mean


def test_preprocess_image_normalizes_known_rgb_value() -> None:
    image = Image.new("RGB", (224, 224), color=(255, 0, 0))

    result = preprocess_image(image)

    expected_red = (1.0 - 0.485) / 0.229
    expected_green = (0.0 - 0.456) / 0.224
    expected_blue = (0.0 - 0.406) / 0.225

    assert result[0, 0, 0] == pytest.approx(expected_red)
    assert result[1, 0, 0] == pytest.approx(expected_green)
    assert result[2, 0, 0] == pytest.approx(expected_blue)


def test_preprocess_image_supports_custom_dimensions() -> None:
    image = Image.new("RGB", (300, 200), color=(100, 100, 100))
    config = ImagePreprocessingConfig(width=128, height=96)

    result = preprocess_image(image, config)

    assert result.shape == (3, 96, 128)


@pytest.mark.parametrize(
    "config",
    [
        ImagePreprocessingConfig(width=0),
        ImagePreprocessingConfig(height=-1),
        ImagePreprocessingConfig(mean=(0.5, 0.5)),  # type: ignore[arg-type]
        ImagePreprocessingConfig(std=(1.0, 0.0, 1.0)),
    ],
)
def test_preprocess_image_rejects_invalid_configuration(
    config: ImagePreprocessingConfig,
) -> None:
    image = Image.new("RGB", (224, 224))

    with pytest.raises(ImagePreprocessingError):
        preprocess_image(image, config)