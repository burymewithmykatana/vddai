from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

UPLOAD_DIRECTORY = Path("uploads")

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class ImageStorageService:
    def __init__(self, upload_directory: Path = UPLOAD_DIRECTORY):
        self.upload_directory = upload_directory

    def save(self, image: UploadFile) -> str:
        extension = ALLOWED_CONTENT_TYPES.get(image.content_type or "")

        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only JPEG, PNG, and WebP images are supported.",
            )

        contents = image.file.read()

        maximum_size_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024

        if len(contents) > maximum_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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

        self.upload_directory.mkdir(parents=True, exist_ok=True)

        #   Generating the filename with uuid4() prevents filename collisions and path-traversal attempts.
        filename = f"{uuid4().hex}{extension}"
        #   uploads/3e866fe6abbe4e1092bf807f3ee866af.jpg
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

        return image_path.as_posix()

    def delete(self, image_path: str) -> None:
        path = Path(image_path)

        if path.exists():
            path.unlink()


image_storage_service = ImageStorageService()
