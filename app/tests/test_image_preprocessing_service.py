from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Generator

import numpy as np
import pytest
from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingError,
    ImagePreprocessingService,
)


@pytest.fixture
def local_tmp_path() -> Generator[Path, None, None]:
    with TemporaryDirectory(
        prefix="vddai-preprocess-test-",
        dir=".",
    ) as temporary_directory:
        yield Path(temporary_directory)


def create_test_image(
    path: Path,
    *,
    size: tuple[int, int] = (32, 24),
    mode: str = "RGB",
    color: int | tuple[int, ...] = (128, 64, 32),
    image_format: str = "PNG",
) -> None:
    image = Image.new(
        mode=mode,
        size=size,
        color=color,
    )
    image.save(path, format=image_format)


def test_preprocess_returns_expected_contract(
    local_tmp_path: Path,
):
    image_path = local_tmp_path / "input.png"

    create_test_image(
        image_path,
        size=(32, 24),
    )

    service = ImagePreprocessingService(
        target_width=16,
        target_height=12,
    )

    result = service.preprocess(image_path)

    assert result.original_width == 32
    assert result.original_height == 24
    assert result.output_width == 16
    assert result.output_height == 12

    assert result.array.shape == (3, 12, 16)
    assert result.array.dtype == np.float32
    assert result.array.flags["C_CONTIGUOUS"]

    assert result.array.min() >= 0.0
    assert result.array.max() <= 1.0


def test_preprocess_converts_grayscale_to_rgb(
    local_tmp_path: Path,
):
    image_path = local_tmp_path / "grayscale.png"

    create_test_image(
        image_path,
        size=(10, 10),
        mode="L",
        color=128,
    )

    service = ImagePreprocessingService(
        target_width=8,
        target_height=8,
    )

    result = service.preprocess(image_path)

    assert result.array.shape == (3, 8, 8)

    assert np.allclose(
        result.array[0],
        result.array[1],
    )
    assert np.allclose(
        result.array[1],
        result.array[2],
    )


def test_preprocess_converts_rgba_to_rgb(
    local_tmp_path: Path,
):
    image_path = local_tmp_path / "transparent.png"

    create_test_image(
        image_path,
        size=(10, 10),
        mode="RGBA",
        color=(100, 150, 200, 50),
    )

    service = ImagePreprocessingService(
        target_width=8,
        target_height=8,
    )

    result = service.preprocess(image_path)

    assert result.array.shape == (3, 8, 8)
    assert result.array.dtype == np.float32
    assert result.array.flags["C_CONTIGUOUS"]


def test_preprocess_rejects_missing_file(
    local_tmp_path: Path,
):
    missing_path = local_tmp_path / "missing.png"

    service = ImagePreprocessingService()

    with pytest.raises(
        ImagePreprocessingError,
        match="Image file does not exist",
    ):
        service.preprocess(missing_path)


def test_preprocess_rejects_invalid_image(
    local_tmp_path: Path,
):
    invalid_path = local_tmp_path / "invalid.jpg"
    invalid_path.write_bytes(b"not-an-image")

    service = ImagePreprocessingService()

    with pytest.raises(
        ImagePreprocessingError,
        match="Image could not be preprocessed",
    ):
        service.preprocess(invalid_path)


@pytest.mark.parametrize(
    ("target_width", "target_height"),
    [
        (0, 224),
        (224, 0),
        (-1, 224),
        (224, -1),
    ],
)
def test_preprocessing_service_rejects_invalid_target_dimensions(
    target_width: int,
    target_height: int,
):
    with pytest.raises(
        ValueError,
        match="Target image dimensions must be positive",
    ):
        ImagePreprocessingService(
            target_width=target_width,
            target_height=target_height,
        )
