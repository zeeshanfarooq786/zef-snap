from __future__ import annotations

import re
import threading
from typing import Any

from . import APP_DISPLAY_NAME, APP_FOOTER, __version__
from .downloader import discover_product_images, download_product_images, open_folder
from .self_updater import update_now
from .theme import asset_path, file_to_data_uri

# NEVER store the pywebview Window on the js_api object.
# pywebview walks public attributes of js_api and recursing into Window.native
# freezes the WinForms UI ("Not Responding") on Windows.
_UI_WINDOW: Any = None


def _preview_url(url: str) -> str:
    """Smaller grid thumbs so WebView2 does not stall loading full 2000px assets."""
    if "scene7.com" in url and "wid=" in url:
        return re.sub(r"wid=\d+", "wid=480", url, count=1).replace("hei=2000", "hei=480")
    if "scene7.com" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}wid=480&hei=480"
    return url


def _sanitize_fetch_result(result: dict) -> dict:
    """Keep bridge payloads small — never send base64 previews through pywebview."""
    image_urls = [str(url) for url in (result.get("images") or []) if url]
    items = [
        {"url": url, "preview": _preview_url(url)}
        for url in image_urls
    ]
    return {
        "url": result.get("url"),
        "slug": result.get("slug"),
        "product_name": result.get("product_name"),
        "images_found": result.get("images_found", len(image_urls)),
        "images": image_urls,
        "items": items,
        "used_js": bool(result.get("used_js")),
        "error": result.get("error"),
    }


class ZefsnapApi:
    """Only methods and underscore-private attrs — public attrs are walked by pywebview."""

    def __init__(self) -> None:
        self._last_result: dict | None = None
        self._last_download: dict | None = None
        self._fetch_status = "idle"
        self._download_status = "idle"
        self._download_progress = ""
        self._busy_lock = threading.Lock()

    def _run_async(self, worker) -> dict:
        # Always return immediately so the WebView UI thread never waits on network I/O.
        threading.Thread(target=worker, daemon=True, name="zefsnap-worker").start()
        return {"status": "started"}

    def get_last_result(self) -> dict:
        if self._last_result:
            return _sanitize_fetch_result(self._last_result)
        return {
            "error": None,
            "images_found": 0,
            "images": [],
            "items": [],
        }

    def get_fetch_status(self) -> str:
        return self._fetch_status

    def get_last_download(self) -> dict:
        result = self._last_download or {"error": "No download result.", "downloaded": []}
        # Keep bridge payloads tiny — paths only, no bulky nested objects.
        return {
            "error": result.get("error"),
            "product_name": result.get("product_name"),
            "output_dir": result.get("output_dir"),
            "downloaded_count": len(result.get("downloaded") or []),
        }

    def get_download_status(self) -> str:
        return self._download_status

    def get_download_progress(self) -> str:
        return self._download_progress

    def fetch_images(self, url: str, high_res: bool = True) -> dict:
        if not self._busy_lock.acquire(blocking=False):
            return {"status": "busy"}
        self._fetch_status = "running"
        self._last_result = None

        def worker() -> None:
            try:
                result = discover_product_images(url, use_js=False, high_res=high_res)
                self._last_result = _sanitize_fetch_result(result)
                self._fetch_status = "done"
            except Exception as exc:
                self._last_result = {
                    "error": str(exc),
                    "images_found": 0,
                    "images": [],
                    "items": [],
                }
                self._fetch_status = "error"
            finally:
                self._busy_lock.release()

        return self._run_async(worker)

    def choose_folder(self) -> str | None:
        window = _UI_WINDOW
        if not window:
            return None
        try:
            import webview

            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            if isinstance(result, tuple) and result:
                return result[0]
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            return None
        return None

    def download_selected(self, url: str, image_urls=None, output_dir: str | None = None) -> dict:
        # Guard against PyWebView arg quirks: folder paths must never be treated as URL lists.
        if isinstance(image_urls, str) and not image_urls.lower().startswith(("http://", "https://")):
            # Likely received output_dir in the image_urls slot.
            if output_dir is None and (":" in image_urls or image_urls.startswith(("/", "\\"))):
                output_dir = image_urls
            image_urls = []
        if isinstance(output_dir, list):
            # Args swapped: treat list as URLs and ignore bad output_dir.
            image_urls = output_dir
            output_dir = None

        from .downloader import _normalize_image_urls

        image_urls = _normalize_image_urls(image_urls)
        if not str(url or "").lower().startswith(("http://", "https://")):
            return {"status": "error", "error": "A valid product URL is required before downloading."}

        if not self._busy_lock.acquire(blocking=False):
            return {"status": "busy"}
        self._download_status = "running"
        self._download_progress = f"0/{len(image_urls)}"
        self._last_download = None

        def progress(index: int, total: int, image_url: str, file_path: str, status: str) -> None:
            self._download_progress = f"{index}/{total}"

        def worker() -> None:
            try:
                if not image_urls:
                    self._last_download = {
                        "error": "No valid image URLs selected.",
                        "downloaded": [],
                        "output_dir": output_dir,
                        "product_name": None,
                    }
                    self._download_status = "error"
                    return
                result = download_product_images(
                    url,
                    output_dir=output_dir if isinstance(output_dir, str) or output_dir is None else None,
                    selected_urls=image_urls,
                    progress_callback=progress,
                )
                self._last_download = result
                self._download_status = "done" if not result.get("error") else "error"
            except Exception as exc:
                self._last_download = {
                    "error": str(exc),
                    "downloaded": [],
                    "output_dir": output_dir if isinstance(output_dir, str) else None,
                    "product_name": None,
                }
                self._download_status = "error"
            finally:
                self._busy_lock.release()

        return self._run_async(worker)

    def open_folder(self, path: str) -> dict:
        try:
            open_folder(path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def update_now(self, asset_url: str | None) -> dict:
        # Never download on the UI/bridge thread — that freezes the window.
        if not self._busy_lock.acquire(blocking=False):
            return {"status": "busy"}

        def worker() -> None:
            try:
                update_now(asset_url)
            finally:
                self._busy_lock.release()

        return self._run_async(worker)


def _html(
    *,
    wordmark_src: str,
    favicon_href: str,
    version: str,
    footer: str,
) -> str:
    wordmark_style = "display:block" if wordmark_src else "display:none"
    fallback_style = "display:none" if wordmark_src else "display:block"
    return (
        r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Zefsnap</title>
  <link id="favicon" rel="icon" href="__FAVICON_HREF__" />
  <style>
    :root {
      --bg: #FBFBFD;
      --surface: #FFFFFF;
      --surface-sunken: #F3F3F5;
      --border: #E4E4E8;
      --text: #181818;
      --text-muted: #6B6B70;
      --accent: #EDA812;
      --accent-hover: #D6960A;
      --accent-tint: #FDF2DC;
      --radius: 8px;
      --hover-shadow: 0 1px 3px rgba(24, 24, 24, 0.06);
      --sp-1: 8px;
      --sp-2: 16px;
      --sp-3: 24px;
      --sp-4: 32px;
      --sp-6: 48px;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      height: 100%;
      overflow: hidden;
      color: var(--text);
      background: var(--bg);
      font-family: -apple-system, "Segoe UI", "Inter", Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    #scrollRoot {
      height: 100vh;
      overflow-y: auto;
      overflow-x: hidden;
      scroll-behavior: smooth;
      background: var(--bg);
    }
    button, input { font: inherit; }
    .app { width: min(1080px, calc(100vw - 48px)); margin: 0 auto; padding: 0 0 var(--sp-6); }

    /* Header */
    header {
      display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
      padding: var(--sp-2) 0; margin-bottom: var(--sp-6);
      border-bottom: 1px solid var(--border);
    }
    .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .brand img {
      display: block;
      height: 30px;
      width: auto;
      max-width: min(200px, 42vw);
      object-fit: contain;
      object-position: left center;
    }
    .brand-fallback { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
    .version {
      font-size: 12px; font-weight: 500; letter-spacing: 0.02em; color: var(--text-muted);
      background: var(--surface-sunken); padding: 4px 10px; border-radius: 999px;
    }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .powered { color: var(--text-muted); font-size: 13px; font-weight: 500; letter-spacing: 0.02em; }

    /* Hero */
    .hero { margin-bottom: var(--sp-6); }
    h1 {
      margin: 0 0 12px; font-size: clamp(28px, 4vw, 36px); font-weight: 600;
      letter-spacing: -0.01em; line-height: 1.15; color: var(--text);
    }
    .subtitle { margin: 0 0 var(--sp-4); color: var(--text-muted); font-size: 15px; line-height: 1.5; max-width: 620px; }
    .input-row { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: stretch; }
    .url-field { position: relative; display: flex; align-items: center; min-width: 0; }
    .url-input {
      width: 100%; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface);
      color: var(--text); padding: 14px 52px 14px 16px; outline: none; font-size: 15px;
      transition: border-color 120ms ease;
    }
    .url-input::placeholder { color: var(--text-muted); }
    .url-input:focus { border-color: var(--accent); }
    .paste-btn {
      position: absolute; right: 6px; width: 36px; height: 36px;
      border: 0; border-radius: var(--radius); background: transparent; color: var(--text-muted);
      display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
      transition: color 120ms ease, background 120ms ease;
    }
    .paste-btn:hover { color: var(--text); background: var(--surface-sunken); }
    .paste-btn svg { width: 18px; height: 18px; }

    /* Buttons — one primary style everywhere */
    .primary {
      border: 0; border-radius: var(--radius); padding: 14px 20px; cursor: pointer;
      background: var(--accent); color: #FFFFFF; font-size: 14px; font-weight: 600;
      transition: background 120ms ease;
    }
    .primary:hover { background: var(--accent-hover); }
    .primary:disabled { opacity: 0.5; cursor: not-allowed; background: var(--accent); }
    /* Text-link style action */
    .link-btn {
      border: 0; background: transparent; padding: 0; cursor: pointer;
      color: var(--text); font-size: 14px; font-weight: 500;
      transition: color 120ms ease;
    }
    .link-btn:hover { color: var(--accent); }
    .link-btn.muted { color: var(--text-muted); }
    .link-btn.muted:hover { color: var(--accent); }

    /* Options row */
    .options {
      display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-3);
      margin-top: var(--sp-2); font-size: 14px;
    }
    .option { display: flex; align-items: center; gap: 8px; color: var(--text); cursor: pointer; }
    .option input { accent-color: var(--accent); width: 16px; height: 16px; }
    .folder-path { color: var(--text-muted); font-size: 13px; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    /* Update banner */
    .banner {
      display: none; align-items: center; justify-content: space-between; gap: var(--sp-2);
      margin-top: var(--sp-3); border: 1px solid var(--border); border-radius: var(--radius);
      background: var(--accent-tint); padding: 12px 16px; font-size: 14px;
    }

    /* Progress */
    .progress-box { display: none; margin-bottom: var(--sp-6); }
    .progress-track { height: 5px; background: var(--surface-sunken); border-radius: 999px; overflow: hidden; }
    .progress-fill { height: 100%; width: 0%; background: var(--accent); border-radius: 999px; transition: width 180ms ease; }
    .status { margin-top: var(--sp-1); color: var(--text-muted); font-size: 13px; }

    /* Results */
    .results { display: none; margin-bottom: var(--sp-6); }
    .results-top {
      display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
      margin-bottom: var(--sp-3); flex-wrap: wrap;
    }
    .results-actions { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
    .count-label { font-size: 13px; font-weight: 500; letter-spacing: 0.02em; color: var(--text-muted); }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--sp-2); }
    .card {
      position: relative; overflow: hidden; border-radius: var(--radius);
      border: 1px solid var(--border); background: var(--surface);
      transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
    }
    .card:hover { transform: translateY(-1px); box-shadow: var(--hover-shadow); }
    .card.selected { border: 2px solid var(--accent); }
    .card img { width: 100%; aspect-ratio: 4/5; object-fit: cover; display: block; background: var(--surface-sunken); cursor: zoom-in; }
    .card-badge {
      position: absolute; top: 8px; left: 8px;
      padding: 3px 8px; border-radius: 999px;
      background: var(--surface); border: 1px solid var(--border);
      color: var(--text); font-size: 12px; font-weight: 500;
    }
    .card-check { position: absolute; top: 8px; right: 8px; }
    .card-check input { accent-color: var(--accent); width: 18px; height: 18px; cursor: pointer; }

    /* Complete */
    .complete {
      display: none; margin-bottom: var(--sp-6); padding: var(--sp-3); border-radius: var(--radius);
      border: 1px solid var(--border); background: var(--surface); font-size: 14px;
    }
    .complete strong { color: var(--accent); font-weight: 600; }
    .complete .open-row { margin-top: var(--sp-2); }

    footer { text-align: center; color: var(--text-muted); font-size: 13px; font-weight: 500; letter-spacing: 0.02em; }
    @media (max-width: 760px) {
      .app { width: calc(100vw - 24px); }
      .input-row { display: flex; flex-direction: column; }
      .results-top { flex-direction: column; align-items: stretch; }
    }
  </style>
</head>
<body>
  <div id="scrollRoot">
  <main class="app">
    <header>
      <div class="brand">
        <img id="wordmark" alt="Zefsnap" src="__WORDMARK_SRC__" style="__WORDMARK_STYLE__" />
        <div id="brandFallback" class="brand-fallback" style="__FALLBACK_STYLE__">Zefsnap</div>
        <span class="version" id="version">v__VERSION__</span>
      </div>
      <div class="header-actions">
        <div class="powered">Powered by Zef Technology</div>
      </div>
    </header>

    <section class="hero">
      <h1>Download product galleries in seconds.</h1>
      <p class="subtitle">Paste a product page URL. Zefsnap finds high-resolution images, lets you review them, and saves the selected set locally.</p>
      <div class="input-row">
        <div class="url-field">
          <input class="url-input" id="url" placeholder="Paste product page URL here" disabled />
          <button class="paste-btn" id="pasteBtn" type="button" title="Paste from clipboard" aria-label="Paste from clipboard" disabled>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="8" y="2" width="12" height="16" rx="2"></rect>
              <path d="M4 6a2 2 0 0 1 2-2h1"></path>
              <path d="M4 10v10a2 2 0 0 0 2 2h10"></path>
            </svg>
          </button>
        </div>
        <button class="primary" id="fetchBtn" disabled>Fetch Images</button>
      </div>
      <div class="options">
        <label class="option"><input type="checkbox" id="highRes" checked /> High-res mode</label>
        <button class="link-btn" id="folderBtn" type="button" disabled>Choose Folder</button>
        <span class="folder-path" id="folderPath">Default: downloads/product-name</span>
      </div>
      <div class="banner" id="updateBanner">
        <span id="updateText"></span>
        <button class="primary" id="updateBtn">Update Now</button>
      </div>
    </section>

    <section class="progress-box" id="progressBox" style="display:block">
      <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
      <div class="status" id="statusText">Starting…</div>
    </section>

    <section class="results" id="results">
      <div class="results-top">
        <span class="count-label" id="countBadge">0 images found</span>
        <div class="results-actions">
          <button class="link-btn muted" id="selectAllBtn" type="button">Select All</button>
          <button class="link-btn muted" id="unselectAllBtn" type="button">Unselect All</button>
          <button class="primary" id="downloadBtn" type="button" disabled>Download Selected</button>
        </div>
      </div>
      <div class="grid" id="grid"></div>
    </section>

    <section class="complete" id="completeBox">
      <div><strong id="productName"></strong> saved to <span id="outputDir"></span></div>
      <div class="open-row"><button class="link-btn" id="openFolderBtn" type="button">Open Folder</button></div>
    </section>

    <footer id="footer">__FOOTER__</footer>
  </main>
  </div>

  <script>
    const state = { images: [], items: [], url: "", folder: null, latestUpdate: null, ready: false };
    const $ = (id) => document.getElementById(id);
    const scrollRoot = () => document.getElementById("scrollRoot");

    function setControlsEnabled(enabled) {
      ["fetchBtn", "pasteBtn", "folderBtn", "downloadBtn", "selectAllBtn", "unselectAllBtn"].forEach((id) => {
        const el = $(id);
        if (el) el.disabled = !enabled;
      });
      const url = $("url");
      if (url) url.disabled = !enabled;
    }

    function ensureReady() {
      if (state.ready && window.pywebview && window.pywebview.api) return true;
      $("statusText").textContent = "App is still starting — wait a second, then try again.";
      $("progressBox").style.display = "block";
      return false;
    }

    window.addEventListener("pywebviewready", () => {
      state.ready = true;
      setControlsEnabled(true);
      $("statusText").textContent = "Ready.";
      $("progressBox").style.display = "none";
    });
    // Fallback if the ready event is missed on some WebView2 builds.
    setTimeout(() => {
      if (state.ready) return;
      if (window.pywebview && window.pywebview.api) {
        state.ready = true;
        setControlsEnabled(true);
        $("statusText").textContent = "Ready.";
        $("progressBox").style.display = "none";
      }
    }, 2500);

    function watchJob(getStatus, onDone, onTick, intervalMs = 600) {
      // Non-blocking poller: never holds the UI waiting on a long Python call chain.
      const timer = setInterval(async () => {
        try {
          const status = await getStatus();
          if (onTick) onTick(status);
          if (status === "done" || status === "error") {
            clearInterval(timer);
            onDone(status);
          }
        } catch (error) {
          // Keep polling; transient bridge glitches should not freeze the window.
        }
      }, intervalMs);
      return timer;
    }

    function normalizeItems(result) {
      if (Array.isArray(result.items) && result.items.length) {
        return result.items.map((item) => ({
          url: String(item.url || ""),
          preview: String(item.preview || item.url || ""),
        }));
      }
      const urls = Array.isArray(result.images) ? result.images : [];
      return urls.map((url) => ({ url: String(url), preview: String(url) }));
    }

    function scrollToElement(element) {
      if (!element) return;
      const root = scrollRoot();
      requestAnimationFrame(() => {
        if (root) {
          const top = element.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 20;
          root.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
        } else {
          element.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }

    function clearPreviousSession() {
      $("results").style.display = "none";
      $("completeBox").style.display = "none";
      $("progressFill").style.width = "0%";
      $("grid").innerHTML = "";
      $("productName").textContent = "";
      $("outputDir").textContent = "";
      $("openFolderBtn").dataset.path = "";
      $("statusText").textContent = "";
      state.images = [];
      state.items = [];
    }

    function renderResults(result) {
      state.items = normalizeItems(result);
      state.images = state.items.map((item) => item.url);
      $("results").style.display = state.items.length ? "block" : "none";
      $("countBadge").textContent = `${state.items.length} images found`;

      const grid = $("grid");
      grid.innerHTML = "";
      state.items.forEach((item, index) => {
        const card = document.createElement("article");
        card.className = "card selected";
        card.dataset.fullUrl = item.url;

        const badge = document.createElement("span");
        badge.className = "card-badge";
        badge.textContent = `#${index + 1}`;

        const checkWrap = document.createElement("label");
        checkWrap.className = "card-check";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "imageCheck";
        checkbox.checked = true;
        checkbox.dataset.index = String(index);
        checkbox.addEventListener("change", () => {
          card.classList.toggle("selected", checkbox.checked);
        });
        checkWrap.appendChild(checkbox);

        const img = document.createElement("img");
        img.alt = `Product image ${index + 1}`;
        img.src = item.preview;
        img.addEventListener("click", () => window.open(item.url, "_blank"));

        card.appendChild(img);
        card.appendChild(badge);
        card.appendChild(checkWrap);
        grid.appendChild(card);
      });

      $("statusText").textContent = result.error || "Images ready.";
      $("completeBox").style.display = "none";
    }

    $("folderBtn").onclick = async () => {
      if (!ensureReady()) return;
      const folder = await window.pywebview.api.choose_folder();
      if (folder) {
        state.folder = folder;
        $("folderPath").textContent = folder;
      }
    };

    $("pasteBtn").onclick = async () => {
      if (!ensureReady()) return;
      // Prefer browser clipboard — never create a Tk window inside PyWebView (deadlocks on Windows).
      let text = "";
      try {
        text = (await navigator.clipboard.readText()).trim();
      } catch (error) {
        text = "";
      }
      if (text) {
        $("url").value = text;
        $("url").focus();
        $("url").setSelectionRange(0, $("url").value.length);
      }
    };

    $("fetchBtn").onclick = async () => {
      if (!ensureReady()) return;
      state.url = $("url").value.trim();
      if (!state.url) return;
      clearPreviousSession();
      $("fetchBtn").disabled = true;
      $("statusText").textContent = "Fetching product page...";
      $("progressBox").style.display = "block";
      $("progressFill").style.width = "18%";
      scrollToElement($("progressBox"));
      const started = await window.pywebview.api.fetch_images(state.url, $("highRes").checked);
      if (started && started.status === "busy") {
        $("statusText").textContent = "Another job is still running. Please wait.";
        $("fetchBtn").disabled = false;
        return;
      }
      watchJob(
        () => window.pywebview.api.get_fetch_status(),
        async () => {
          const result = await window.pywebview.api.get_last_result();
          renderResults(result);
          $("progressFill").style.width = result.images_found ? "100%" : "0%";
          $("fetchBtn").disabled = false;
          if (state.items.length) {
            setTimeout(() => scrollToElement($("results")), 120);
          }
        },
        () => {
          $("statusText").textContent = "Fetching product images...";
          const width = Math.min(85, parseInt($("progressFill").style.width || "18", 10) + 4);
          $("progressFill").style.width = `${width}%`;
        }
      );
    };

    function setAllSelected(selected) {
      document.querySelectorAll(".imageCheck").forEach((box) => {
        box.checked = selected;
        box.closest(".card")?.classList.toggle("selected", selected);
      });
    }

    $("selectAllBtn").onclick = () => setAllSelected(true);
    $("unselectAllBtn").onclick = () => setAllSelected(false);

    $("downloadBtn").onclick = async () => {
      if (!ensureReady()) return;
      const selected = [...document.querySelectorAll(".imageCheck")]
        .filter((box) => box.checked)
        .map((box) => box.closest(".card")?.dataset.fullUrl || state.items[Number(box.dataset.index)]?.url)
        .filter((url) => typeof url === "string" && /^https?:\/\//i.test(url));
      if (!selected.length) {
        $("statusText").textContent = "Select at least one image to download.";
        return;
      }
      if (!state.url || !/^https?:\/\//i.test(state.url)) {
        $("statusText").textContent = "Product URL is missing. Fetch images again first.";
        return;
      }
      $("downloadBtn").disabled = true;
      $("completeBox").style.display = "none";
      $("progressBox").style.display = "block";
      $("progressFill").style.width = "5%";
      $("statusText").textContent = "Downloading selected images...";
      scrollToElement($("progressBox"));
      const folder = (typeof state.folder === "string" && state.folder) ? state.folder : null;
      const started = await window.pywebview.api.download_selected(state.url, selected, folder);
      if (started && started.status === "busy") {
        $("statusText").textContent = "Another job is still running. Please wait.";
        $("downloadBtn").disabled = false;
        return;
      }
      watchJob(
        () => window.pywebview.api.get_download_status(),
        async () => {
          const result = await window.pywebview.api.get_last_download();
          $("downloadBtn").disabled = false;
          if (!result.error) {
            $("completeBox").style.display = "block";
            $("productName").textContent = result.product_name;
            $("outputDir").textContent = result.output_dir;
            $("openFolderBtn").dataset.path = result.output_dir;
            $("progressFill").style.width = "100%";
            $("statusText").textContent = "Download complete.";
          } else {
            $("statusText").textContent = result.error;
          }
        },
        async () => {
          try {
            const progress = await window.pywebview.api.get_download_progress();
            if (progress && progress.includes("/")) {
              const [current, total] = progress.split("/");
              const percent = total && Number(total) ? Math.round((Number(current) / Number(total)) * 100) : 10;
              $("progressFill").style.width = `${Math.max(5, percent)}%`;
              $("statusText").textContent = `Downloading ${progress}...`;
            }
          } catch (error) {}
        }
      );
    };

    $("openFolderBtn").onclick = async () => {
      await window.pywebview.api.open_folder($("openFolderBtn").dataset.path);
    };

    $("updateBtn").onclick = async () => {
      if (!state.latestUpdate) return;
      $("updateText").textContent = "Downloading update...";
      await window.pywebview.api.update_now(state.latestUpdate.assetUrl);
    };

  </script>
</body>
</html>"""
        .replace("__FAVICON_HREF__", favicon_href)
        .replace("__WORDMARK_SRC__", wordmark_src)
        .replace("__WORDMARK_STYLE__", wordmark_style)
        .replace("__FALLBACK_STYLE__", fallback_style)
        .replace("__VERSION__", version)
        .replace("__FOOTER__", footer)
    )


def _quiet_pywebview_logs() -> None:
    """Silence the noisy WinForms attribute-walk recursion errors on Windows.

    Some pywebview + WebView2 combinations spam
    'Error while processing window.native... maximum recursion depth exceeded'
    to the pywebview logger. These are harmless but flood the console, so we
    raise the logger threshold above ERROR.
    """
    import logging

    logging.getLogger("pywebview").setLevel(logging.CRITICAL)


def run() -> None:
    global _UI_WINDOW

    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("Install PyWebView first: pip install pywebview") from exc

    _quiet_pywebview_logs()

    wordmark = asset_path("logo images", "wordmark-small.png")
    # Do not embed icon.png (large). A missing favicon is fine and keeps startup light.
    html = _html(
        wordmark_src=file_to_data_uri(wordmark),
        favicon_href="",
        version=__version__,
        footer=APP_FOOTER,
    )

    api = ZefsnapApi()
    icon = asset_path("logo images", "icon.ico")

    kwargs = {
        "title": APP_DISPLAY_NAME,
        "html": html,
        "js_api": api,
        "width": 1180,
        "height": 820,
        "min_size": (920, 680),
        "background_color": "#FBFBFD",
    }
    if icon.exists():
        kwargs["icon"] = str(icon)

    try:
        window = webview.create_window(**kwargs)
    except TypeError:
        kwargs.pop("icon", None)
        window = webview.create_window(**kwargs)

    # Keep the Window off the js_api instance (see _UI_WINDOW note above).
    _UI_WINDOW = window

    # http_server=True serves the UI over localhost instead of injecting raw
    # HTML, which avoids the native-object serialization path that triggers the
    # WinForms recursion spam on some Windows 10 WebView2 builds.
    webview.start(debug=False, http_server=True)


if __name__ == "__main__":
    run()
