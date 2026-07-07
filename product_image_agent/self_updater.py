from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import GITHUB_RELEASES_API, __version__
from .net import fetch_bytes, fetch_text

INSTALLER_NAME = "ZefsnapSetup.exe"
USER_AGENT = "Zefsnap"


def _configured() -> bool:
    return "<REPLACE-WITH-MY-GITHUB-USERNAME>" not in GITHUB_RELEASES_API


def check_for_update() -> dict:
    if not _configured():
        return {"configured": False, "current": __version__}

    payload = json.loads(
        fetch_text(
            GITHUB_RELEASES_API,
            timeout=20,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
        )
    )
    latest = str(payload.get("tag_name") or "").lstrip("v")
    if not latest:
        return {"configured": True, "current": __version__, "updateAvailable": False}

    asset_url = None
    asset_name = None
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        if name == INSTALLER_NAME:
            asset_url = asset.get("browser_download_url")
            asset_name = name
            break
    if not asset_url:
        for asset in payload.get("assets") or []:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".exe"):
                asset_url = asset.get("browser_download_url")
                asset_name = name
                break

    return {
        "configured": True,
        "current": __version__,
        "latest": latest,
        "updateAvailable": _is_newer(latest, __version__),
        "releaseNotes": str(payload.get("body") or ""),
        "assetUrl": asset_url,
        "assetName": asset_name,
    }


def _is_newer(latest: str, current: str) -> bool:
    def parts(value: str) -> list[int]:
        return [int(part) for part in value.split(".") if part.isdigit()]

    return parts(latest) > parts(current)


def download_update(asset_url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        fetch_bytes(asset_url, timeout=120, headers={"User-Agent": USER_AGENT})
    )
    return destination


def install_update(asset_url: str) -> dict:
    installer = Path(tempfile.gettempdir()) / f"Zefsnap_setup_{int(time.time())}.exe"
    download_update(asset_url, installer)
    subprocess.Popen(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
        ],
        close_fds=True,
    )
    os._exit(0)


def update_now(asset_url: str | None) -> dict:
    if not asset_url:
        return {"ok": False, "error": "No installer download URL was provided."}
    install_update(asset_url)
    return {"ok": True}
