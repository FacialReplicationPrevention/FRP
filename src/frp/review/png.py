"""Minimal PNG writing (for synthetic fixtures) and structural PNG sanitising (for serving).

Media are untrusted (V12). :func:`sanitise_png` never decodes pixels: it parses the chunk structure
with strict bounds, verifies every CRC, checks the header against the expected dimensions and
rebuilds the file from the critical chunks only (``IHDR``, ``PLTE``, ``IDAT``, ``IEND``). Every
ancillary chunk is dropped, which removes text, EXIF, ICC, time and animation metadata. Pixel
decoding is left to the browser's sandboxed image decoder; that is a residual risk, not a
guarantee. No imaging library is imported.
"""

from __future__ import annotations

import struct
import zlib
from typing import Final

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES: Final = 16 * 1024 * 1024
MAX_DIMENSION: Final = 4096
_CRITICAL: Final = frozenset({b"IHDR", b"PLTE", b"IDAT", b"IEND"})
# Allowed (colour type -> bit depths) combinations from the PNG specification.
_VALID_DEPTHS: Final = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}


class MediaRejected(Exception):
    """A media file failed structural validation. The message is a fixed description."""


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def encode_png_rgb(width: int, height: int, rows: list[bytes]) -> bytes:
    """Encode 8-bit RGB rows (``width * 3`` bytes each) as a PNG with no ancillary chunks."""
    if len(rows) != height or any(len(row) != width * 3 for row in rows):
        raise ValueError("rows do not match the declared dimensions")
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def sanitise_png(
    data: bytes, *, expected_width: int | None = None, expected_height: int | None = None
) -> bytes:
    """Return a rebuilt PNG with only critical chunks, or raise :class:`MediaRejected`."""
    if len(data) > MAX_PNG_BYTES:
        raise MediaRejected("media file exceeds the size limit")
    if not data.startswith(PNG_SIGNATURE):
        raise MediaRejected("media file is not a PNG")
    position = len(PNG_SIGNATURE)
    kept: list[bytes] = []
    seen_ihdr = seen_idat = seen_iend = False
    idat_closed = False
    while position < len(data):
        if seen_iend:
            raise MediaRejected("data after the PNG end chunk")
        if position + 8 > len(data):
            raise MediaRejected("truncated PNG chunk header")
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        end = position + 12 + length
        if length > MAX_PNG_BYTES or end > len(data):
            raise MediaRejected("truncated or oversized PNG chunk")
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            raise MediaRejected("invalid PNG chunk type")
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(">I", data[position + 8 + length : end])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise MediaRejected("PNG chunk checksum mismatch")
        position = end
        if not seen_ihdr and kind != b"IHDR":
            raise MediaRejected("PNG must start with a header chunk")
        if kind[0] >= 97:  # ancillary chunk: metadata, dropped
            if seen_idat:
                idat_closed = True
            continue
        if kind not in _CRITICAL:
            raise MediaRejected("unknown critical PNG chunk")
        if kind == b"IHDR":
            if seen_ihdr or length != 13:
                raise MediaRejected("invalid PNG header")
            seen_ihdr = True
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", body
            )
            if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
                raise MediaRejected("PNG dimensions are outside the permitted range")
            if depth not in _VALID_DEPTHS.get(colour, set()):
                raise MediaRejected("invalid PNG colour type or bit depth")
            if compression != 0 or filtering != 0 or interlace not in (0, 1):
                raise MediaRejected("unsupported PNG compression, filter or interlace method")
            if (expected_width is not None and width != expected_width) or (
                expected_height is not None and height != expected_height
            ):
                raise MediaRejected("PNG dimensions differ from the catalogue")
        elif kind == b"IDAT":
            if idat_closed:
                raise MediaRejected("PNG image data chunks are not contiguous")
            seen_idat = True
        elif kind == b"PLTE" and seen_idat:
            raise MediaRejected("PNG palette after image data")
        elif kind == b"IEND":
            seen_iend = True
        kept.append(_chunk(kind, body))
    if not (seen_ihdr and seen_idat and seen_iend):
        raise MediaRejected("PNG is missing required chunks")
    return PNG_SIGNATURE + b"".join(kept)


__all__ = ["MAX_PNG_BYTES", "MediaRejected", "encode_png_rgb", "sanitise_png"]
