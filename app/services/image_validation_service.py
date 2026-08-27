from dataclasses import dataclass
from io import BytesIO
import warnings

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.services.image_dimension_policy import (
    DecodedImageTooLargeError,
    enforce_decoded_image_pixel_limit,
)

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
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
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
                    if width <= 0 or height <= 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The uploaded image has invalid dimensions.",
                        )

                    enforce_decoded_image_pixel_limit(
                        width=width,
                        height=height,
                        maximum_pixels=settings.MAX_IMAGE_PIXELS,
                    )
                    image.verify()

        except HTTPException:
            raise
        except (
            DecodedImageTooLargeError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Image exceeds the maximum decoded size of "
                    f"{settings.MAX_IMAGE_PIXELS} pixels."
                ),
            ) from exc
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is not a valid image.",
            ) from exc

        return ValidatedImage(
            format=detected_format,
            extension=metadata["extension"],
            width=width,
            height=height,
        )


image_validation_service = ImageValidationService()
