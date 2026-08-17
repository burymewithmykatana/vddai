from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

FloatImageArray = NDArray[np.float32]


class ImagePreprocessingError(Exception):
    """Raised when a stored image cannot be converted into model input."""


@dataclass(frozen=True)
class PreprocessedImage:
    array: FloatImageArray
    original_width: int
    original_height: int
    output_width: int
    output_height: int


class ImagePreprocessingService:
    def __init__(
        self,
        target_width: int = settings.MODEL_IMAGE_WIDTH,
        target_height: int = settings.MODEL_IMAGE_HEIGHT,
    ):
        if target_width <= 0 or target_height <= 0:
            raise ValueError("Target image dimensions must be positive.")

        self.target_width = target_width
        self.target_height = target_height

    def preprocess(self, image_path: str | Path) -> PreprocessedImage:
        path = Path(image_path)

        if not path.is_file():
            raise ImagePreprocessingError(
                f"Image file does not exist: {path.as_posix()}"
            )

        return self._preprocess_source(path, source_description=path.as_posix())

    def preprocess_bytes(self, contents: bytes) -> PreprocessedImage:
        return self._preprocess_source(
            BytesIO(contents),
            source_description="stored image object",
        )

    def _preprocess_source(
        self,
        source: str | Path | BinaryIO,
        *,
        source_description: str,
    ) -> PreprocessedImage:
        try:
            with Image.open(source) as image:
                original_width, original_height = image.size

                oriented_image = ImageOps.exif_transpose(image)
                rgb_image = oriented_image.convert("RGB")

                resized_image = rgb_image.resize(
                    (self.target_width, self.target_height),
                    resample=Image.Resampling.BILINEAR,
                )

                array = np.asarray(
                    resized_image,
                    dtype=np.float32,
                )

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImagePreprocessingError(
                f"Image could not be preprocessed: {source_description}"
            ) from exc

        array /= 255.0

        # Pillow/NumPy produces HWC:
        # (height, width, channels)
        #
        # Most PyTorch models expect CHW:
        # (channels, height, width)
        array = np.transpose(array, (2, 0, 1))

        array = np.ascontiguousarray(
            array,
            dtype=np.float32,
        )

        expected_shape = (
            3,
            self.target_height,
            self.target_width,
        )

        if array.shape != expected_shape:
            raise ImagePreprocessingError(
                (
                    "Unexpected preprocessed image shape. "
                    f"Expected {expected_shape}, received {array.shape}."
                )
            )

        if not np.isfinite(array).all():
            raise ImagePreprocessingError(
                "Preprocessed image contains non-finite values."
            )

        return PreprocessedImage(
            array=array,
            original_width=original_width,
            original_height=original_height,
            output_width=self.target_width,
            output_height=self.target_height,
        )


image_preprocessing_service = ImagePreprocessingService()
