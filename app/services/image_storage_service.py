from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.image_validation_service import image_validation_service


class ImageStorageError(Exception):
    """Raised when a storage backend cannot complete an object operation."""


class InvalidImageObjectKeyError(ImageStorageError, ValueError):
    """Raised when an object key is unsafe or outside the supported grammar."""


class StoredImageNotFoundError(ImageStorageError):
    """Raised when a requested stored image object does not exist."""


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    size_bytes: int


@dataclass(frozen=True)
class StoredImage:
    object_key: str
    format: str
    width: int
    height: int


class ImageObjectStore(Protocol):
    """Backend-independent object operations used by API and worker services."""

    def write(self, object_key: str, contents: bytes) -> StoredObject:
        """Persist bytes under one server-generated opaque object key."""

    def read(self, object_key: str) -> bytes:
        """Return the complete stored object."""

    def delete(self, object_key: str) -> bool:
        """Delete an object, returning false when it was already absent."""

    def exists(self, object_key: str) -> bool:
        """Return whether a regular stored object exists."""


_KEY_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class LocalFilesystemImageObjectStore:
    """Map opaque object keys to files below one configured local root."""

    def __init__(self, root_directory: str | Path) -> None:
        self.root_directory = Path(root_directory)

    def _resolve_object_path(self, object_key: str) -> Path:
        if not isinstance(object_key, str) or not object_key:
            raise InvalidImageObjectKeyError("Image object key must be non-empty.")

        components = object_key.split("/")
        if (
            object_key.startswith("/")
            or "\\" in object_key
            or any(
                component in {"", ".", ".."}
                or _KEY_COMPONENT_PATTERN.fullmatch(component) is None
                for component in components
            )
        ):
            raise InvalidImageObjectKeyError("Image object key is unsafe.")

        root = self.root_directory.resolve(strict=False)
        object_path = root.joinpath(*components).resolve(strict=False)
        if object_path == root or not object_path.is_relative_to(root):
            raise InvalidImageObjectKeyError(
                "Image object key escapes the configured storage root."
            )
        return object_path

    def write(self, object_key: str, contents: bytes) -> StoredObject:
        object_path = self._resolve_object_path(object_key)
        created = False
        try:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            with object_path.open("xb") as destination:
                created = True
                written = destination.write(contents)
        except OSError as exc:
            if created:
                try:
                    object_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ImageStorageError(
                f"Image object could not be written: {object_key}"
            ) from exc

        if written != len(contents):
            try:
                object_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ImageStorageError(f"Image object write was incomplete: {object_key}")

        return StoredObject(object_key=object_key, size_bytes=written)

    def read(self, object_key: str) -> bytes:
        object_path = self._resolve_object_path(object_key)
        try:
            return object_path.read_bytes()
        except FileNotFoundError as exc:
            raise StoredImageNotFoundError(
                f"Stored image object does not exist: {object_key}"
            ) from exc
        except OSError as exc:
            raise ImageStorageError(
                f"Stored image object could not be read: {object_key}"
            ) from exc

    def delete(self, object_key: str) -> bool:
        object_path = self._resolve_object_path(object_key)
        try:
            object_path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ImageStorageError(
                f"Stored image object could not be deleted: {object_key}"
            ) from exc
        return True

    def exists(self, object_key: str) -> bool:
        return self._resolve_object_path(object_key).is_file()


class ImageStorageService:
    """Validate uploads and coordinate backend-independent object storage."""

    def __init__(self, object_store: ImageObjectStore) -> None:
        self.object_store = object_store

    def store(self, image: UploadFile) -> StoredImage:
        try:
            contents = image.file.read()

            maximum_size_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024

            if len(contents) > maximum_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"Image exceeds the maximum size of "
                        f"{settings.MAX_IMAGE_SIZE_MB} MB."
                    ),
                )

            if not contents:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded image is empty.",
                )

            validated_image = image_validation_service.validate(
                contents=contents,
                declared_content_type=image.content_type,
            )

            object_key = f"predictions/{uuid4().hex}{validated_image.extension}"
            try:
                stored_object = self.object_store.write(object_key, contents)
            except ImageStorageError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="The uploaded image could not be stored.",
                ) from exc
        finally:
            image.file.close()

        return StoredImage(
            object_key=stored_object.object_key,
            format=validated_image.format,
            width=validated_image.width,
            height=validated_image.height,
        )

    def read(self, object_key: str) -> bytes:
        return self.object_store.read(object_key)

    def delete(self, object_key: str) -> bool:
        return self.object_store.delete(object_key)

    def exists(self, object_key: str) -> bool:
        return self.object_store.exists(object_key)


def build_image_storage_service() -> ImageStorageService:
    if settings.IMAGE_STORAGE_BACKEND == "local":
        return ImageStorageService(
            LocalFilesystemImageObjectStore(settings.IMAGE_STORAGE_ROOT)
        )
    raise RuntimeError("Unsupported image storage backend.")


image_storage_service = build_image_storage_service()
