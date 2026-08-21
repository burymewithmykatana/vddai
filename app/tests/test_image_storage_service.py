from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.models.prediction import Prediction
from app.services.image_storage_service import (
    ImageStorageError,
    ImageStorageService,
    InvalidImageObjectKeyError,
    LocalFilesystemImageObjectStore,
    StoredImageNotFoundError,
    StoredObject,
)
from app.services.image_validation_service import ValidatedImage


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 6), color=(120, 80, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(*, filename: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(_png_bytes()),
        filename=filename,
        headers=Headers({"content-type": "image/png"}),
    )


def test_store_generates_opaque_key_without_trusting_uploaded_filename(
    tmp_path: Path,
) -> None:
    object_store = LocalFilesystemImageObjectStore(tmp_path / "objects")
    service = ImageStorageService(object_store)

    stored = service.store(_upload(filename="../../client-selected-name-and-path.png"))

    assert re.fullmatch(r"predictions/[0-9a-f]{32}\.png", stored.object_key)
    assert "client-selected" not in stored.object_key
    assert object_store.read(stored.object_key) == _png_bytes()


def test_local_object_store_round_trip(tmp_path: Path) -> None:
    object_store = LocalFilesystemImageObjectStore(tmp_path / "objects")
    object_key = "predictions/0123456789abcdef.png"
    contents = b"stored-image-bytes"

    metadata = object_store.write(object_key, contents)

    assert metadata.object_key == object_key
    assert metadata.size_bytes == len(contents)
    assert object_store.exists(object_key) is True
    assert object_store.read(object_key) == contents
    assert object_store.delete(object_key) is True
    assert object_store.exists(object_key) is False


@pytest.mark.parametrize(
    "object_key",
    [
        "../outside.png",
        "predictions/../../outside.png",
        "/absolute/path.png",
        "predictions\\outside.png",
        "C:/outside.png",
        "predictions//outside.png",
        "predictions/./outside.png",
    ],
)
def test_local_object_store_rejects_keys_that_could_escape_root(
    tmp_path: Path,
    object_key: str,
) -> None:
    root = tmp_path / "objects"
    object_store = LocalFilesystemImageObjectStore(root)

    with pytest.raises(InvalidImageObjectKeyError):
        object_store.write(object_key, b"unsafe")

    assert not (tmp_path / "outside.png").exists()


def test_delete_missing_object_is_idempotent(tmp_path: Path) -> None:
    object_store = LocalFilesystemImageObjectStore(tmp_path / "objects")

    assert object_store.delete("predictions/missing.png") is False
    assert object_store.delete("predictions/missing.png") is False


def test_read_missing_object_has_explicit_failure(tmp_path: Path) -> None:
    object_store = LocalFilesystemImageObjectStore(tmp_path / "objects")

    with pytest.raises(StoredImageNotFoundError, match="does not exist"):
        object_store.read("predictions/missing.png")


def test_failed_duplicate_write_preserves_existing_object(tmp_path: Path) -> None:
    object_store = LocalFilesystemImageObjectStore(tmp_path / "objects")
    object_key = "predictions/existing.png"
    object_store.write(object_key, b"original")

    with pytest.raises(ImageStorageError, match="could not be written"):
        object_store.write(object_key, b"replacement")

    assert object_store.read(object_key) == b"original"


def test_prediction_object_key_keeps_legacy_physical_column_name() -> None:
    mapped_column = Prediction.image_object_key.property.columns[0]

    assert mapped_column.name == "image_path"
    assert Prediction.__table__.c.image_path is mapped_column


class ReadSizeTrackingBuffer(BytesIO):
    def __init__(self, contents: bytes) -> None:
        super().__init__(contents)
        self.requested_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(size)


@dataclass
class RecordingObjectStore:
    contents: bytes | None = None

    def write(self, object_key: str, contents: bytes) -> StoredObject:
        self.contents = contents
        return StoredObject(object_key=object_key, size_bytes=len(contents))

    def read(self, object_key: str) -> bytes:
        assert self.contents is not None
        return self.contents

    def delete(self, object_key: str) -> bool:
        self.contents = None
        return True

    def exists(self, object_key: str) -> bool:
        return self.contents is not None


def test_store_reads_only_limit_plus_one_and_accepts_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.services import image_storage_service as storage_module

    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)
    monkeypatch.setattr(
        storage_module.image_validation_service,
        "validate",
        lambda **kwargs: ValidatedImage(
            format="PNG",
            extension=".png",
            width=8,
            height=6,
        ),
    )
    contents = b"x" * (1024 * 1024)
    buffer = ReadSizeTrackingBuffer(contents)
    object_store = RecordingObjectStore()
    service = ImageStorageService(object_store)
    upload = UploadFile(
        file=buffer,
        filename="boundary.png",
        size=None,
        headers=Headers({"content-type": "image/png"}),
    )

    service.store(upload)

    assert buffer.requested_sizes == [1024 * 1024 + 1]
    assert object_store.contents == contents


def test_store_rejects_limit_plus_one_without_unbounded_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)
    buffer = ReadSizeTrackingBuffer(b"x" * (1024 * 1024 + 1))
    object_store = RecordingObjectStore()
    service = ImageStorageService(object_store)
    upload = UploadFile(
        file=buffer,
        filename="oversized.png",
        size=None,
        headers=Headers({"content-type": "image/png"}),
    )

    with pytest.raises(Exception) as exc_info:
        service.store(upload)

    assert getattr(exc_info.value, "status_code", None) == 413
    assert buffer.requested_sizes == [1024 * 1024 + 1]
    assert object_store.contents is None


def test_store_rejects_reported_oversize_without_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)
    buffer = ReadSizeTrackingBuffer(b"small")
    service = ImageStorageService(RecordingObjectStore())
    upload = UploadFile(
        file=buffer,
        filename="reported-oversized.png",
        size=1024 * 1024 + 1,
        headers=Headers({"content-type": "image/png"}),
    )

    with pytest.raises(Exception) as exc_info:
        service.store(upload)

    assert getattr(exc_info.value, "status_code", None) == 413
    assert buffer.requested_sizes == []
