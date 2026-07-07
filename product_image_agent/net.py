from __future__ import annotations

import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import certifi

_SSL_CONTEXT: ssl.SSLContext | None = None


def ca_bundle_path() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        candidates = [
            meipass / "certifi" / "cacert.pem",
            exe_dir / "_internal" / "certifi" / "cacert.pem",
            exe_dir / "certifi" / "cacert.pem",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return certifi.where()


def ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = ssl.create_default_context(cafile=ca_bundle_path())
    return _SSL_CONTEXT


def urlopen_safe(request: Request, timeout: int = 30):
    return urlopen(request, timeout=timeout, context=ssl_context())


def fetch_bytes(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers=headers or {})
    with urlopen_safe(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> str:
    return fetch_bytes(url, timeout=timeout, headers=headers).decode("utf-8", errors="ignore")


def verify_ssl_connectivity() -> str:
    """Quick HTTPS smoke test used by the frozen exe `--verify-ssl` flag."""
    from . import GITHUB_RELEASES_API

    text = fetch_text(
        GITHUB_RELEASES_API,
        timeout=15,
        headers={"User-Agent": "Zefsnap", "Accept": "application/vnd.github+json"},
    )
    return text[:120]
