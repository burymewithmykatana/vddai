from pathlib import Path
from uuid import uuid4
from dataclasses import dataclass


from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.image_validation_service import image_validation_service

UPLOAD_DIRECTORY = Path("uploads")


@dataclass(frozen=True)
class StoredImage:
    path: str
    format: str
    width: int
    height: int


class ImageStorageService:
    def __init__(self, upload_directory: Path = UPLOAD_DIRECTORY):
        self.upload_directory = upload_directory

    def save(self, image: UploadFile) -> StoredImage:
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

        self.upload_directory.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid4().hex}{validated_image.extension}"
        image_path = self.upload_directory / filename

        try:
            image_path.write_bytes(contents)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The uploaded image could not be stored.",
            ) from exc
        finally:
            image.file.close()

        return StoredImage(
            path=image_path.as_posix(),
            format=validated_image.format,
            width=validated_image.width,
            height=validated_image.height,
        )

    def delete(self, image_path: str) -> None:
        path = Path(image_path)

        if path.exists():
            path.unlink()


image_storage_service = ImageStorageService()
