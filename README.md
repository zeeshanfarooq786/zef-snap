<p align="center">
  <img src="logo images/wordmark-full.png" alt="Zefsnap" width="360" />
</p>

# Zefsnap — by Zef Technology

**Zefsnap** downloads high-resolution product gallery images from ecommerce product pages. Paste a product URL, preview the detected images, deselect anything you do not want, and save the selected set locally.

`Zefsnap • Powered by Zef Technology`

## What Zefsnap Includes

- A modern **PyWebView desktop app** with a dark/light premium UI.
- A preserved **CLI** for scripting and fast terminal use.
- Site-specific fast paths for **Quince**, **FJackets**, and **Angel Jackets**.
- A stronger generic extractor for other product websites.
- High-resolution URL upgrading for common CDN thumbnail patterns.
- Optional Playwright rendering for JavaScript-heavy pages.
- PyInstaller packaging as `Zefsnap.exe`.
- GitHub Releases self-update support.

## Logo Assets

Place the final logo folder at the project root:

```text
logo images/
├── icon.ico
├── icon.png
├── wordmark-full.png
└── wordmark-small.png
```

Zefsnap samples `logo images/icon.png` at runtime and derives the app theme from the actual logo colors. The warm amber color becomes the primary accent, and the near-black color drives text and dark surfaces.

## Requirements

- Python 3.10+
- `pywebview` for the desktop app
- `pyinstaller` for building `Zefsnap.exe`
- Optional: `playwright` for JavaScript fallback extraction

Install desktop/build dependencies:

```bash
pip install -r requirements.txt
```

Optional JavaScript extraction support:

```bash
pip install -r requirements-optional.txt
python -m playwright install chromium
```

## Desktop App

Run the Zefsnap GUI:

```bash
python zefsnap.py
```

The GUI includes:

- Header with the Zefsnap wordmark and "Powered by Zef Technology"
- URL input and **Fetch Images** button
- Dry-run, folder picker, JavaScript fallback, and high-res toggles
- Responsive result grid with image checkboxes
- Download progress bar and per-file status
- Output confirmation with **Open Folder**
- Dark/light theme toggle

## CLI Usage

Preview URLs without downloading:

```bash
python download_images.py "https://www.quince.com/men/100-leather-flight-jacket-with-shearling-collar?color=true-black&gender=men" --dry-run
```

Download images:

```bash
python download_images.py "https://www.fjackets.com/buy/womens-black-real-leather-moto-jacket.html"
```

Use a custom output folder:

```bash
python download_images.py "https://www.angeljackets.com/products/johnson-women-tan-quilted-fitted-motorcycle-leather-jacket.html" -o ./my-images
```

Enable JavaScript fallback only if static extraction finds zero images:

```bash
python download_images.py "<product-url>" --js
```

Disable high-resolution URL rewriting:

```bash
python download_images.py "<product-url>" --no-high-res
```

JSON output:

```bash
python download_images.py "<product-url>" --json
```

Images are saved to `downloads/<product-slug>/` by default.

## Extraction Strategy

Zefsnap extracts product images in this order:

1. JSON-LD Product structured data
2. Open Graph and Twitter image meta tags
3. Highest-resolution `srcset` candidates from `<img>` and `<source>`
4. High-resolution URL upgrades for query params and CDN suffixes
5. Gallery/zoom attributes such as `data-zoom-image`, `data-large_image`, and lazy `data-src`
6. Images inside common product gallery containers

The specialized Quince, FJackets, and Angel Jackets extractors still run first for speed and accuracy, but they also benefit from the shared high-resolution resolver.

## Build Windows EXE

Build a single-file Windows executable:

```bash
pyinstaller build.spec
```

or:

```bash
python build.py
```

The output is:

```text
dist/Zefsnap.exe
```

`logo images/icon.ico` is used as the executable icon when present, and `logo images/` is bundled as app data.

## Self-Updates

Zefsnap checks GitHub Releases on startup through:

```text
https://api.github.com/repos/<REPLACE-WITH-MY-GITHUB-USERNAME>/zefsnap/releases/latest
```

Before publishing, replace the placeholder in `product_image_agent/__init__.py` with your real GitHub username/repo path. When a newer release exists and includes `Zefsnap.exe`, the app shows an update banner and can download, replace, and relaunch itself using a temporary batch helper.

The workflow at `.github/workflows/release.yml` builds and publishes `dist/Zefsnap.exe` on every push to `main`.

## Python API

```python
from product_image_agent.downloader import download_product_images

result = download_product_images("https://www.quince.com/men/...")
print(result["downloaded"])
```

Discover images without downloading:

```python
from product_image_agent.downloader import discover_product_images

result = discover_product_images("https://example.com/products/item", use_js=False, high_res=True)
print(result["images"])
```

## Notes

- Respect each website's terms of service and robots.txt.
- For Quince, pass the `color=` query param to download images for a specific color variant.
- Playwright is optional and only used when requested and static HTML extraction finds zero images.
- If `logo images/` is missing during development, Zefsnap uses safe fallback colors and text branding.

---

`Zefsnap • Powered by Zef Technology`
