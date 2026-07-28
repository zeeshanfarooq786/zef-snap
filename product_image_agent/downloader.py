from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from .extractors import (
    API_EXTRACTORS,
    BROWSER_HEADERS,
    USER_AGENT,
    extract_product_images,
    prettify_slug,
    slug_from_url,
)
from .net import urlopen_safe


def _normalize_image_urls(value) -> list[str]:
    """Coerce bridge/CLI input into a clean list of http(s) URLs.

    PyWebView sometimes passes a Windows folder path (e.g. D:\\...) as a string
    where a URL list is expected. Iterating that string yields 'D', which makes
    urllib raise: unknown url type: d.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        value = [value.decode() if isinstance(value, bytes) else value]
    if not isinstance(value, (list, tuple, set)):
        value = [value]

    urls: list[str] = []
    for item in value:
        text = str(item).strip()
        if text.lower().startswith(("http://", "https://")):
            urls.append(text)
    return urls


def fetch_page(url: str, timeout: int = 30) -> str:
    headers = dict(BROWSER_HEADERS)
    request = Request(url, headers=headers)
    with urlopen_safe(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def is_challenge_html(html: str) -> bool:
    """True when the body is a bot/CDN interstitial (e.g. Cloudflare) instead of a product page."""
    lower = (html or "").lower()
    if not lower:
        return True
    markers = (
        "just a moment...",
        "cf-browser-verification",
        "challenge-platform",
        "cdn-cgi/challenge",
        "attention required! | cloudflare",
        "enable javascript and cookies to continue",
    )
    return any(marker in lower for marker in markers)


def fetch_page_with_js(url: str, timeout_ms: int = 30000) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install it with "
            "`pip install playwright` and `python -m playwright install chromium`."
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        html = page.content()
        browser.close()
        return html


def filename_from_url(url: str, index: int) -> str:
    path = urlparse(url).path
    name = Path(path).name or f"image_{index:02d}.jpg"
    name = re.sub(r"[^\w.\-]", "_", name)
    if not Path(name).suffix:
        name += ".jpg"
    return f"{index:02d}_{name}"


def _extension_from_bytes(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and b"avif" in data[8:16]:
        return ".avif"
    return None


def download_image(url: str, dest: Path, timeout: int = 60, referer: str | None = None) -> Path:
    if not str(url).lower().startswith(("http://", "https://")):
        raise ValueError(f"Not a valid image URL: {url!r}")
    headers = {
        "User-Agent": USER_AGENT,
        # Prefer JPEG so Windows viewers can open the file; avoid AVIF/WebP negotiation.
        "Accept": "image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-origin" if referer else "cross-site",
    }
    if referer:
        headers["Referer"] = referer
    else:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
            headers["Sec-Fetch-Site"] = "same-origin"
    request = Request(url, headers=headers)
    with urlopen_safe(request, timeout=timeout) as response:
        data = response.read()

    real_ext = _extension_from_bytes(data)
    if real_ext and dest.suffix.lower() != real_ext:
        dest = dest.with_suffix(real_ext)
    dest.write_bytes(data)
    return dest


def _result(
    product_url: str,
    image_urls: list[str],
    *,
    used_js: bool = False,
    error: str | None = None,
) -> dict:
    slug = slug_from_url(product_url)
    return {
        "url": product_url,
        "slug": slug,
        "product_name": prettify_slug(slug),
        "images_found": len(image_urls),
        "images": image_urls,
        "used_js": used_js,
        "error": error if error is not None else (
            None if image_urls else "No product images found on this page."
        ),
    }


def discover_product_images(
    product_url: str,
    *,
    use_js: bool = False,
    high_res: bool = True,
    html: str | None = None,
    browser_html_fetcher=None,
) -> dict:
    # Some luxury sites block HTML (403) but still expose images via API/CDN.
    api_error = None
    for extractor in API_EXTRACTORS:
        if not extractor.matches(product_url):
            continue
        try:
            image_urls = extractor.extract_from_url(product_url, high_res=high_res)
            if image_urls:
                return _result(product_url, image_urls)
        except Exception as exc:
            api_error = str(exc)

    used_js = False
    page_html = html
    block_error: str | None = None

    if page_html is None:
        try:
            page_html = fetch_page(product_url)
        except HTTPError as exc:
            if exc.code in {401, 403, 429}:
                block_error = (
                    f"This website blocked the request (HTTP {exc.code}). "
                    "Cloudflare / bot-protected stores need a real browser session."
                )
            else:
                raise

    if page_html and is_challenge_html(page_html):
        block_error = block_error or (
            "This website returned a bot-protection challenge page instead of the product."
        )
        page_html = None

    if page_html is None and browser_html_fetcher is not None:
        try:
            page_html = browser_html_fetcher(product_url)
            used_js = True
        except Exception as exc:
            block_error = f"{block_error or 'Browser fetch failed.'} ({exc})"
            page_html = None
        if page_html and is_challenge_html(page_html):
            block_error = (
                "The browser still hit a bot-protection challenge. "
                "Open the product URL once in Edge/Chrome, then try again."
            )
            page_html = None

    if page_html is None and use_js:
        try:
            page_html = fetch_page_with_js(product_url)
            used_js = True
        except Exception as exc:
            block_error = f"{block_error or 'Playwright fetch failed.'} ({exc})"
            page_html = None
        if page_html and is_challenge_html(page_html):
            page_html = None

    if page_html is None:
        message = block_error or "Could not load the product page."
        if api_error:
            message = f"{message} API fallback also failed: {api_error}"
        return _result(product_url, [], error=message)

    image_urls = extract_product_images(page_html, product_url, high_res=high_res)

    if not image_urls and use_js and not used_js:
        page_html = fetch_page_with_js(product_url)
        image_urls = extract_product_images(page_html, product_url, high_res=high_res)
        used_js = True

    return _result(product_url, image_urls, used_js=used_js)


def download_urls(
    image_urls: list[str],
    output_dir: str | Path,
    *,
    referer: str | None = None,
    progress_callback=None,
) -> list[dict[str, str]]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, str]] = []
    total = len(image_urls)
    for index, image_url in enumerate(image_urls, start=1):
        filename = filename_from_url(image_url, index)
        dest = folder / filename
        if progress_callback:
            progress_callback(index, total, image_url, str(dest), "downloading")
        saved = download_image(image_url, dest, referer=referer)
        item = {"url": image_url, "file": str(saved)}
        downloaded.append(item)
        if progress_callback:
            progress_callback(index, total, image_url, str(saved), "done")
    return downloaded


def open_folder(path: str | Path) -> None:
    folder = Path(path)
    if os.name == "nt":
        os.startfile(folder)  # type: ignore[attr-defined]
        return
    raise RuntimeError("Open folder is currently implemented for Windows builds.")


def download_product_images(
    product_url: str,
    output_dir: str | Path | None = None,
    *,
    dry_run: bool = False,
    use_js: bool = False,
    high_res: bool = True,
    selected_urls: list[str] | None = None,
    progress_callback=None,
) -> dict:
    # When the GUI already has selected URLs, skip rediscovery so Download
    # does not re-hit the network before saving files.
    if selected_urls is not None:
        image_urls = _normalize_image_urls(selected_urls)
        slug = slug_from_url(product_url)
        product_name = prettify_slug(slug)
        used_js = False
        discover_error = None if image_urls else "No valid image URLs selected."
        discovered = {
            "slug": slug,
            "product_name": product_name,
            "used_js": used_js,
            "error": discover_error,
        }
    else:
        discovered = discover_product_images(product_url, use_js=use_js, high_res=high_res)
        image_urls = _normalize_image_urls(discovered["images"])

    if not image_urls:
        return {
            "url": product_url,
            "slug": discovered.get("slug"),
            "product_name": discovered.get("product_name"),
            "images_found": 0,
            "downloaded": [],
            "output_dir": None,
            "used_js": discovered.get("used_js", False),
            "error": discovered["error"],
        }

    slug = discovered["slug"]
    folder = Path(output_dir) if output_dir else Path("downloads") / slug
    # Luxury CDNs (e.g. Louis Vuitton) require the product page as Referer,
    # not just the site root.
    referer = product_url if product_url.startswith("http") else None
    if not dry_run:
        downloaded = download_urls(
            image_urls,
            folder,
            referer=referer,
            progress_callback=progress_callback,
        )
    else:
        downloaded = []

    if dry_run:
        for index, image_url in enumerate(image_urls, start=1):
            filename = filename_from_url(image_url, index)
            dest = folder / filename
            downloaded.append({"url": image_url, "file": str(dest)})

    return {
        "url": product_url,
        "images_found": len(image_urls),
        "slug": slug,
        "product_name": discovered["product_name"],
        "images": image_urls,
        "downloaded": downloaded,
        "output_dir": str(folder),
        "used_js": discovered["used_js"],
        "error": None,
    }
