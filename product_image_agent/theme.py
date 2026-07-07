from __future__ import annotations

import base64
import json
import os
import sys
import zlib
from collections import Counter
from pathlib import Path

_DATA_URI_CACHE: dict[str, str] = {}


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        internal = exe_dir / "_internal"
        if internal.is_dir():
            return exe_dir
        return exe_dir
    return Path(__file__).resolve().parents[1]


def asset_path(*parts: str) -> Path:
    root = project_root()
    if getattr(sys, "frozen", False):
        internal = root / "_internal"
        candidates = [root.joinpath(*parts), internal.joinpath(*parts)]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return root.joinpath(*parts)


def _theme_cache_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Zefsnap"
    base.mkdir(parents=True, exist_ok=True)
    return base / "theme_cache.json"


def file_to_data_uri(path: Path) -> str:
    key = str(path.resolve())
    cached = _DATA_URI_CACHE.get(key)
    if cached is not None:
        return cached
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "ico": "image/x-icon",
        "svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    uri = f"data:{mime};base64,{encoded}"
    _DATA_URI_CACHE[key] = uri
    return uri


def sample_logo_theme(icon_path: Path | None = None) -> dict[str, str]:
    icon_path = icon_path or asset_path("logo images", "icon.png")
    if not icon_path.exists():
        return default_theme()

    stamp = icon_path.stat().st_mtime
    cache_path = _theme_cache_path()
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("stamp") == stamp and isinstance(cached.get("theme"), dict):
                return cached["theme"]
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    theme = _sample_logo_theme_uncached(icon_path)
    try:
        cache_path.write_text(
            json.dumps({"stamp": stamp, "theme": theme}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return theme


def _sample_logo_theme_uncached(icon_path: Path) -> dict[str, str]:
    pixels = _read_png_pixels(icon_path, max_samples=4096)
    if not pixels:
        return default_theme()

    opaque = [pixel[:3] for pixel in pixels if pixel[3] > 128]
    if not opaque:
        return default_theme()

    counts = Counter(opaque)
    dominant = counts.most_common(1)[0][0]
    accent = _brighten(dominant, 1.15)
    return {
        "accent": _rgb_to_hex(accent),
        "accentSoft": _rgb_to_hex(_brighten(dominant, 1.35)),
        "accentDark": _rgb_to_hex(_darken(dominant, 0.75)),
        "surface": "#F6F4EF",
        "surfaceAlt": "#FFFFFF",
        "text": "#1F1B16",
        "muted": "#6B645C",
        "border": "#E4DDD3",
    }


def default_theme() -> dict[str, str]:
    return {
        "accent": "#C45A2C",
        "accentSoft": "#E8A07A",
        "accentDark": "#8B3D1A",
        "surface": "#F6F4EF",
        "surfaceAlt": "#FFFFFF",
        "text": "#1F1B16",
        "muted": "#6B645C",
        "border": "#E4DDD3",
    }


def _read_png_pixels(path: Path, max_samples: int = 4096) -> list[tuple[int, int, int, int]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return []

    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat = bytearray()

    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = int.from_bytes(data[pos : pos + 4], "big")
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length

        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if not width or not height or bit_depth != 8 or color_type not in (2, 6):
        return []

    raw = zlib.decompress(bytes(idat))
    stride = width * (4 if color_type == 6 else 3)
    rows: list[bytes] = []
    offset = 0
    for _ in range(height):
        if offset >= len(raw):
            break
        offset += 1
        rows.append(raw[offset : offset + stride])
        offset += stride

    step = max(1, int(((width * height) / max(1, max_samples)) ** 0.5))
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(0, height, step):
        row = rows[y]
        for x in range(0, width, step):
            idx = x * (4 if color_type == 6 else 3)
            if color_type == 6:
                r, g, b, a = row[idx : idx + 4]
                pixels.append((r, g, b, a))
            else:
                r, g, b = row[idx : idx + 3]
                pixels.append((r, g, b, 255))
    return pixels


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _brighten(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, int(channel * factor)) for channel in rgb)


def _darken(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(channel * factor)) for channel in rgb)
