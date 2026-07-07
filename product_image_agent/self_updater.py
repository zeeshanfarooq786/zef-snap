from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from . import APP_NAME, GITHUB_RELEASES_API, __version__
from .extractors import USER_AGENT


def _version_tuple(value: str) -> tuple[int, ...]:
    clean = value.strip().lstrip("vV")
    parts: list[int] = []
    for item in clean.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)


def _request_json(url: str, timeout: int = 10) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_update(api_url: str = GITHUB_RELEASES_API) -> dict:
    if "https://api.github.com/repos/zeeshanfarooq786/zef-snap/releases/latest" in api_url:
        return {
            "available": False,
            "configured": False,
            "current_version": __version__,
            "latest_version": None,
            "asset_url": None,
            "message": "Set your GitHub Releases API URL before enabling updates.",
        }

    try:
        release = _request_json(api_url)
    except Exception as exc:
        return {
            "available": False,
            "configured": True,
            "current_version": __version__,
            "latest_version": None,
            "asset_url": None,
            "message": f"Update check failed: {exc}",
        }

    tag = str(release.get("tag_name") or "").lstrip("v")
    asset_url = None
    for asset in release.get("assets", []):
        name = str(asset.get("name") or "")
        if name.lower() == f"{APP_NAME}.exe".lower() or name.lower().endswith(".exe"):
            asset_url = asset.get("browser_download_url")
            break

    available = bool(tag and asset_url and _version_tuple(tag) > _version_tuple(__version__))
    return {
        "available": available,
        "configured": True,
        "current_version": __version__,
        "latest_version": tag,
        "asset_url": asset_url,
        "release_url": release.get("html_url"),
        "message": None if available else "No update available.",
    }


def _running_exe_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path.cwd() / f"{APP_NAME}.exe"


def download_update(asset_url: str, destination: Path) -> None:
    request = Request(asset_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def install_update(asset_url: str) -> dict:
    current_exe = _running_exe_path()
    if current_exe.name.lower() != f"{APP_NAME}.exe".lower() and getattr(sys, "frozen", False):
        current_exe = current_exe.with_name(f"{APP_NAME}.exe")

    new_exe = current_exe.with_name(f"{APP_NAME}_new.exe")
    download_update(asset_url, new_exe)

    batch_path = Path(tempfile.gettempdir()) / f"{APP_NAME}_update_{int(time.time())}.bat"
    batch = f"""@echo off
set OLD="{current_exe}"
set NEW="{new_exe}"
set APP="{current_exe}"
:wait
timeout /t 1 /nobreak >nul
del %OLD% >nul 2>nul
if exist %OLD% goto wait
move /y %NEW% %APP% >nul
start "" %APP%
del "%~f0"
"""
    batch_path.write_text(batch, encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(batch_path)], close_fds=True)
    os._exit(0)


def update_now(asset_url: str | None) -> dict:
    if not asset_url:
        return {"ok": False, "message": "No update asset URL available."}
    try:
        install_update(asset_url)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Updating Zefsnap..."}
