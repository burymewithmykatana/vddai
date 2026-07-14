from dataclasses import dataclass
from io import BytesIO

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError

FORMAT_METADATA = {
    "JPEG": {
        "content_type": "image/jpeg",
        "extension": ".jpg",
    },
    "PNG": {
        "content_type": "image/png",
        "extension": ".png",
    },
    "WEBP": {
        "content_type": "image/webp",
        "extension": ".webp",
    },
}


@dataclass(frozen=True)
class ValidatedImage:
    format: str
    extension: str
    width: int
    height: int


class ImageValidationService:
    def validate(
        self,
        contents: bytes,
        declared_content_type: str | None,
    ) -> ValidatedImage:
        try:
            with Image.open(BytesIO(contents)) as image:
                detected_format = image.format

                if detected_format is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The uploaded file is not a valid image.",
                    )

                detected_format = detected_format.upper()
                metadata = FORMAT_METADATA.get(detected_format)

                if metadata is None:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Only JPEG, PNG, and WebP images are supported.",
                    )

                if declared_content_type != metadata["content_type"]:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail=(
                            "The declared file type does not match "
                            "the uploaded image."
                        ),
                    )

                width, height = image.size

                image.verify()

        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is not a valid image.",
            ) from exc

        if width <= 0 or height <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded image has invalid dimensions.",
            )

        return ValidatedImage(
            format=detected_format,
            extension=metadata["extension"],
            width=width,
            height=height,
        )


image_validation_service = ImageValidationService()
