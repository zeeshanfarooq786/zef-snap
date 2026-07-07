from __future__ import annotations

import struct
import zlib
from pathlib import Path

FALLBACK_AMBER = "#D89B2B"
FALLBACK_DARK = "#101216"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def asset_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)


def _read_png_pixels(path: Path) -> list[tuple[int, int, int, int]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return []

    offset = 8
    width = height = color_type = bit_depth = None
    compressed = b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if bit_depth != 8 or interlace != 0 or color_type not in (2, 6):
                return []
        elif chunk_type == b"IDAT":
            compressed += chunk_data
        elif chunk_type == b"IEND":
            break

    if not width or not height or color_type is None:
        return []

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(compressed)
    rows: list[bytes] = []
    pos = 0
    previous = bytearray(stride)
    for _row in range(height):
        filter_type = raw[pos]
        pos += 1
        scanline = bytearray(raw[pos : pos + stride])
        pos += stride
        for i in range(stride):
            left = scanline[i - channels] if i >= channels else 0
            up = previous[i]
            upper_left = previous[i - channels] if i >= channels else 0
            if filter_type == 1:
                scanline[i] = (scanline[i] + left) & 0xFF
            elif filter_type == 2:
                scanline[i] = (scanline[i] + up) & 0xFF
            elif filter_type == 3:
                scanline[i] = (scanline[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = _paeth(left, up, upper_left)
                scanline[i] = (scanline[i] + predictor) & 0xFF
        previous = scanline
        rows.append(bytes(scanline))

    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for i in range(0, len(row), channels):
            r, g, b = row[i], row[i + 1], row[i + 2]
            a = row[i + 3] if channels == 4 else 255
            if a > 24:
                pixels.append((r, g, b, a))
    return pixels


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def sample_logo_theme(icon_path: Path | None = None) -> dict[str, str]:
    icon_path = icon_path or asset_path("logo images", "icon.png")
    if not icon_path.exists():
        return _theme(FALLBACK_AMBER, FALLBACK_DARK)

    try:
        pixels = _read_png_pixels(icon_path)
    except Exception:
        pixels = []
    if not pixels:
        return _theme(FALLBACK_AMBER, FALLBACK_DARK)

    bucket_counts: dict[tuple[int, int, int], int] = {}
    for r, g, b, _a in pixels:
        bucket = ((r // 16) * 16, (g // 16) * 16, (b // 16) * 16)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    ranked = sorted(bucket_counts.items(), key=lambda item: item[1], reverse=True)
    dark = min((rgb for rgb, _count in ranked), key=lambda rgb: sum(rgb))

    def amber_score(rgb: tuple[int, int, int]) -> int:
        r, g, b = rgb
        saturation = max(rgb) - min(rgb)
        warmth = r + g - (2 * b)
        return saturation + warmth

    amber_candidates = [
        rgb for rgb, _count in ranked if rgb[0] >= rgb[2] and rgb[1] >= rgb[2] and sum(rgb) > 120
    ]
    amber = max(amber_candidates or [ranked[0][0]], key=amber_score)
    return _theme(_hex(amber), _hex(dark))


def _theme(accent: str, near_black: str) -> dict[str, str]:
    return {
        "accent": accent,
        "accent_hover": accent,
        "near_black": near_black,
        "dark_bg": "#0B0D10",
        "dark_panel": "#14171D",
        "dark_panel_2": "#1B1F27",
        "light_bg": "#F6F4EF",
        "light_panel": "#FFFFFF",
        "muted": "#9CA3AF",
        "border": "#2B303B",
        "footer": "Zefsnap • Powered by Zef Technology",
    }
