class DecodedImageTooLargeError(ValueError):
    """Raised when source image dimensions exceed the decoded-pixel budget."""


def enforce_decoded_image_pixel_limit(
    *,
    width: int,
    height: int,
    maximum_pixels: int,
) -> None:
    if width * height > maximum_pixels:
        raise DecodedImageTooLargeError(
            f"Decoded image exceeds the maximum of {maximum_pixels} pixels."
        )
