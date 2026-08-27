from io import BytesIO
import struct
import zlib

from PIL import Image


def png_with_declared_dimensions(*, width: int, height: int) -> bytes:
    """Return a tiny PNG whose checked IHDR declares the requested dimensions."""
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(120, 80, 40)).save(buffer, format="PNG")
    contents = bytearray(buffer.getvalue())
    contents[16:24] = struct.pack(">II", width, height)
    contents[29:33] = struct.pack(
        ">I",
        zlib.crc32(contents[12:29]) & 0xFFFFFFFF,
    )
    return bytes(contents)
