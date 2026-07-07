from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .extractors import USER_AGENT, extract_product_images, prettify_slug, slug_from_url


def fetch_page(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


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


def download_image(url: str, dest: Path, timeout: int = 60) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        dest.write_bytes(response.read())


def discover_product_images(
    product_url: str,
    *,
    use_js: bool = False,
    high_res: bool = True,
) -> dict:
    html = fetch_page(product_url)
    image_urls = extract_product_images(html, product_url, high_res=high_res)
    used_js = False

    if not image_urls and use_js:
        html = fetch_page_with_js(product_url)
        image_urls = extract_product_images(html, product_url, high_res=high_res)
        used_js = True

    slug = slug_from_url(product_url)
    return {
        "url": product_url,
        "slug": slug,
        "product_name": prettify_slug(slug),
        "images_found": len(image_urls),
        "images": image_urls,
        "used_js": used_js,
        "error": None if image_urls else "No product images found on this page.",
    }


def download_urls(
    image_urls: list[str],
    output_dir: str | Path,
    *,
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
        download_image(image_url, dest)
        item = {"url": image_url, "file": str(dest)}
        downloaded.append(item)
        if progress_callback:
            progress_callback(index, total, image_url, str(dest), "done")
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
    discovered = discover_product_images(product_url, use_js=use_js, high_res=high_res)
    image_urls = selected_urls if selected_urls is not None else discovered["images"]

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
    if not dry_run:
        downloaded = download_urls(image_urls, folder, progress_callback=progress_callback)
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
