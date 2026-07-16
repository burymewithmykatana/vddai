from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps


FloatImageArray = NDArray[np.float32]


@dataclass(frozen=True)
class ImagePreprocessingConfig:
    width: int = 224
    height: int = 224

    # Standard ImageNet normalization values.
    mean: tuple[float, float, float] = (
        0.485,
        0.456,
        0.406,
    )
    std: tuple[float, float, float] = (
        0.229,
        0.224,
        0.225,
    )


DEFAULT_PREPROCESSING_CONFIG = ImagePreprocessingConfig()


class ImagePreprocessingError(ValueError):
    """Raised when an image cannot be converted to the model input contract."""


def preprocess_image(
    image: Image.Image,
    config: ImagePreprocessingConfig = DEFAULT_PREPROCESSING_CONFIG,
) -> FloatImageArray:
    """
    Convert a decoded Pillow image into a deterministic model-ready array.

    Contract:
    - EXIF orientation is applied.
    - Input is converted to RGB.
    - Image is resized and center-cropped to the configured dimensions.
    - Pixel values are converted to float32 in [0, 1].
    - ImageNet channel normalization is applied.
    - Output uses channel-first layout: (C, H, W).
    """

    _validate_config(config)

    try:
        oriented_image = ImageOps.exif_transpose(image)
        rgb_image = oriented_image.convert("RGB")

        resized_image = ImageOps.fit(
            rgb_image,
            size=(config.width, config.height),
            method=Image.Resampling.BILINEAR,
            centering=(0.5, 0.5),
        )
    except (OSError, ValueError) as exc:
        raise ImagePreprocessingError(
            "Failed to normalize image orientation, color mode, or size."
        ) from exc

    pixel_array = np.asarray(resized_image, dtype=np.float32)

    expected_shape = (config.height, config.width, 3)
    if pixel_array.shape != expected_shape:
        raise ImagePreprocessingError(
            f"Unexpected image shape {pixel_array.shape}; "
            f"expected {expected_shape}."
        )

    pixel_array /= 255.0

    mean = np.asarray(config.mean, dtype=np.float32)
    std = np.asarray(config.std, dtype=np.float32)

    normalized_array = (pixel_array - mean) / std

    # HWC → CHW. np.ascontiguousarray prevents negative or unusual strides
    # from causing problems in later tensor conversion.
    channel_first_array = np.ascontiguousarray(
        normalized_array.transpose(2, 0, 1),
        dtype=np.float32,
    )

    return channel_first_array


def _validate_config(config: ImagePreprocessingConfig) -> None:
    if config.width <= 0 or config.height <= 0:
        raise ImagePreprocessingError(
            "Preprocessing width and height must be positive."
        )

    if len(config.mean) != 3 or len(config.std) != 3:
        raise ImagePreprocessingError(
            "RGB preprocessing requires three mean and standard-deviation values."
        )

    if any(value <= 0 for value in config.std):
        raise ImagePreprocessingError(
            "Normalization standard deviations must be greater than zero."
        )