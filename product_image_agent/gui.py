from __future__ import annotations

from . import APP_DISPLAY_NAME, APP_FOOTER, APP_NAME, COMPANY_NAME, __version__
from .downloader import discover_product_images, download_product_images, open_folder
from .self_updater import check_for_update, update_now
from .theme import asset_path, file_to_data_uri, sample_logo_theme


class ZefsnapApi:
    def __init__(self) -> None:
        self.window = None
        self.last_result: dict | None = None

    def get_config(self) -> dict:
        theme = sample_logo_theme()
        icon_png = asset_path("logo images", "icon.png")
        wordmark = asset_path("logo images", "wordmark-full.png")
        small_wordmark = asset_path("logo images", "wordmark-small.png")
        return {
            "appName": APP_NAME,
            "company": COMPANY_NAME,
            "displayName": APP_DISPLAY_NAME,
            "footer": APP_FOOTER,
            "version": __version__,
            "theme": theme,
            "assets": {
                "icon": file_to_data_uri(icon_png),
                "wordmark": file_to_data_uri(wordmark),
                "smallWordmark": file_to_data_uri(small_wordmark),
            },
        }

    def paste_clipboard(self) -> str:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            try:
                return str(root.clipboard_get()).strip()
            finally:
                root.destroy()
        except Exception:
            return ""

    def fetch_images(self, url: str, high_res: bool = True) -> dict:
        try:
            result = discover_product_images(url, use_js=False, high_res=high_res)
            self.last_result = result
            return result
        except Exception as exc:
            return {"error": str(exc), "images_found": 0, "images": []}

    def choose_folder(self) -> str | None:
        if not self.window:
            return None
        try:
            import webview

            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            if isinstance(result, tuple) and result:
                return result[0]
            if isinstance(result, list) and result:
                return result[0]
        except Exception:
            return None
        return None

    def download_selected(self, url: str, image_urls: list[str], output_dir: str | None = None) -> dict:
        def progress(index: int, total: int, image_url: str, file_path: str, status: str) -> None:
            if self.window:
                safe = {
                    "index": index,
                    "total": total,
                    "url": image_url,
                    "file": file_path,
                    "status": status,
                }
                self.window.evaluate_js(f"window.zefsnapProgress({safe!r})")

        try:
            result = download_product_images(
                url,
                output_dir=output_dir,
                selected_urls=image_urls,
                progress_callback=progress,
            )
            return result
        except Exception as exc:
            return {"error": str(exc), "downloaded": [], "output_dir": output_dir}

    def open_folder(self, path: str) -> dict:
        try:
            open_folder(path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def check_update(self) -> dict:
        return check_for_update()

    def update_now(self, asset_url: str | None) -> dict:
        return update_now(asset_url)


def _html() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Zefsnap</title>
  <link id="favicon" rel="icon" href="" />
  <style>
    :root {
      --accent: #D89B2B;
      --accent-hover: #D89B2B;
      --near-black: #101216;
      --bg: #0B0D10;
      --panel: #14171D;
      --panel-2: #1B1F27;
      --text: #F8FAFC;
      --muted: #9CA3AF;
      --border: #2B303B;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }
    [data-theme="light"] {
      --bg: #F6F4EF;
      --panel: #FFFFFF;
      --panel-2: #F1EEE7;
      --text: #101216;
      --muted: #667085;
      --border: #DED8CC;
      --shadow: 0 24px 70px rgba(16, 18, 22, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at top left, color-mix(in srgb, var(--accent) 18%, transparent), transparent 32rem),
        linear-gradient(135deg, var(--bg), color-mix(in srgb, var(--bg) 88%, var(--near-black)));
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    button, input { font: inherit; }
    .app { width: min(1180px, calc(100vw - 48px)); margin: 0 auto; padding: 24px 0 36px; }
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 20px; border: 1px solid var(--border); border-radius: 24px;
      background: color-mix(in srgb, var(--panel) 88%, transparent);
      box-shadow: var(--shadow); backdrop-filter: blur(18px);
    }
    .brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
    .brand img {
      display: block;
      height: 34px;
      width: auto;
      max-width: min(220px, 42vw);
      object-fit: contain;
      object-position: left center;
    }
    .brand-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .brand-fallback { font-size: 24px; font-weight: 850; letter-spacing: -0.05em; }
    .version { color: var(--muted); font-size: 12px; margin-top: 3px; }
    .powered { color: var(--muted); font-size: 13px; }
    .header-actions { display: flex; align-items: center; gap: 14px; }
    .theme-toggle {
      border: 1px solid var(--border); background: var(--panel-2); color: var(--text);
      border-radius: 999px; padding: 9px 13px; cursor: pointer; transition: 180ms ease;
    }
    .theme-toggle:hover { border-color: var(--accent); transform: translateY(-1px); }
    .hero {
      margin-top: 28px; padding: 36px; border-radius: 32px; background: var(--panel);
      border: 1px solid var(--border); box-shadow: var(--shadow);
    }
    h1 { margin: 0 0 10px; font-size: clamp(34px, 5vw, 60px); letter-spacing: -0.07em; line-height: 0.95; }
    .subtitle { margin: 0 0 28px; color: var(--muted); font-size: 16px; max-width: 680px; }
    .input-row { display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: stretch; }
    .url-field {
      position: relative;
      display: flex;
      align-items: center;
      min-width: 0;
    }
    .url-input {
      width: 100%; border: 1px solid var(--border); border-radius: 20px; background: var(--panel-2);
      color: var(--text); padding: 18px 56px 18px 20px; outline: none; transition: 180ms ease;
    }
    .paste-btn {
      position: absolute;
      right: 8px;
      width: 40px;
      height: 40px;
      border: 1px solid transparent;
      border-radius: 14px;
      background: color-mix(in srgb, var(--panel) 70%, transparent);
      color: var(--muted);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: 180ms ease;
    }
    .paste-btn:hover {
      color: var(--text);
      border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
      background: color-mix(in srgb, var(--accent) 14%, var(--panel-2));
      transform: translateY(-1px);
    }
    .paste-btn svg { width: 18px; height: 18px; }
    .url-input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 18%, transparent); }
    .primary, .secondary {
      border: 0; border-radius: 18px; padding: 16px 22px; cursor: pointer;
      transition: 180ms ease; font-weight: 760;
    }
    .primary { background: var(--accent); color: #101216; box-shadow: 0 12px 28px color-mix(in srgb, var(--accent) 25%, transparent); }
    .primary:hover { transform: translateY(-1px); filter: brightness(1.05); }
    .primary:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }
    .secondary { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
    .secondary:hover { border-color: var(--accent); }
    .options {
      display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 18px; color: var(--muted);
    }
    .option {
      display: flex; align-items: center; gap: 9px; border: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel-2) 85%, transparent); padding: 10px 14px; border-radius: 999px;
    }
    .option input { accent-color: var(--accent); }
    .folder-path { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .banner {
      display: none; align-items: center; justify-content: space-between; gap: 14px;
      margin-top: 18px; border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
      background: color-mix(in srgb, var(--accent) 12%, var(--panel)); padding: 13px 16px; border-radius: 18px;
    }
    .results { display: none; margin-top: 24px; }
    .results-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
    .results-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .btn-group {
      display: inline-flex;
      align-items: stretch;
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      background: var(--panel-2);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
    }
    .btn-group .group-btn {
      border: 0;
      border-right: 1px solid var(--border);
      border-radius: 0;
      padding: 12px 16px;
      min-width: 108px;
    }
    .btn-group .group-btn:last-child { border-right: 0; }
    .btn-group .group-btn.active {
      background: color-mix(in srgb, var(--accent) 16%, var(--panel-2));
      color: var(--text);
    }
    .badge { background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px; padding: 9px 13px; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
    .card {
      position: relative; overflow: hidden; border-radius: 22px; border: 1px solid var(--border);
      background: var(--panel); box-shadow: 0 12px 40px rgba(0,0,0,.16);
    }
    .card img { width: 100%; aspect-ratio: 4/5; object-fit: cover; display: block; background: var(--panel-2); }
    .card label {
      position: absolute; top: 10px; left: 10px; display: flex; align-items: center; gap: 7px;
      padding: 7px 10px; border-radius: 999px; background: rgba(0,0,0,.62); color: white; font-size: 12px;
    }
    .progress-box {
      display: none; margin-top: 22px; padding: 18px; border-radius: 22px; background: var(--panel);
      border: 1px solid var(--border);
    }
    .progress-track { height: 12px; background: var(--panel-2); border-radius: 999px; overflow: hidden; }
    .progress-fill { height: 100%; width: 0%; background: var(--accent); transition: width 180ms ease; }
    .status { margin-top: 10px; color: var(--muted); font-size: 14px; }
    .complete {
      display: none; margin-top: 18px; padding: 18px; border-radius: 22px; border: 1px solid var(--border);
      background: var(--panel);
    }
    .complete strong { color: var(--accent); }
    footer { margin-top: 22px; text-align: center; color: var(--muted); font-size: 13px; }
    @media (max-width: 760px) {
      .app { width: min(100vw - 24px, 1180px); }
      header, .input-row, .results-top { grid-template-columns: 1fr; flex-direction: column; align-items: stretch; }
      .hero { padding: 24px; }
      .input-row { display: flex; flex-direction: column; }
    }
  </style>
</head>
<body data-theme="dark">
  <main class="app">
    <header>
      <div class="brand">
        <img id="wordmark" alt="Zefsnap" />
        <div class="brand-meta">
          <div id="brandFallback" class="brand-fallback">Zefsnap</div>
          <div class="version" id="version"></div>
        </div>
      </div>
      <div class="header-actions">
        <div class="powered">Powered by Zef Technology</div>
        <button class="theme-toggle" id="themeBtn">Dark</button>
      </div>
    </header>

    <section class="hero">
      <h1>Download product galleries in seconds.</h1>
      <p class="subtitle">Paste a product page URL. Zefsnap finds high-resolution images, lets you review them, and saves the selected set locally.</p>
      <div class="input-row">
        <div class="url-field">
          <input class="url-input" id="url" placeholder="Paste product page URL here" />
          <button class="paste-btn" id="pasteBtn" type="button" title="Paste from clipboard" aria-label="Paste from clipboard">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="8" y="2" width="12" height="16" rx="2"></rect>
              <path d="M4 6a2 2 0 0 1 2-2h1"></path>
              <path d="M4 10v10a2 2 0 0 0 2 2h10"></path>
            </svg>
          </button>
        </div>
        <button class="primary" id="fetchBtn">Fetch Images</button>
      </div>
      <div class="options">
        <label class="option"><input type="checkbox" id="highRes" checked /> High-res mode</label>
        <button class="secondary" id="folderBtn" type="button">Choose Folder</button>
        <span class="folder-path" id="folderPath">Default: downloads/product-name</span>
      </div>
      <div class="banner" id="updateBanner">
        <span id="updateText"></span>
        <button class="primary" id="updateBtn">Update Now</button>
      </div>
    </section>

    <section class="results" id="results">
      <div class="results-top">
        <span class="badge" id="countBadge">0 images found</span>
        <div class="results-actions">
          <div class="btn-group" role="group" aria-label="Selection controls">
            <button class="secondary group-btn" id="selectAllBtn" type="button">Select All</button>
            <button class="secondary group-btn" id="unselectAllBtn" type="button">Unselect All</button>
          </div>
          <button class="primary" id="downloadBtn" type="button">Download Selected</button>
        </div>
      </div>
      <div class="grid" id="grid"></div>
    </section>

    <section class="progress-box" id="progressBox">
      <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
      <div class="status" id="statusText">Waiting...</div>
    </section>

    <section class="complete" id="completeBox">
      <div><strong id="productName"></strong> saved to <span id="outputDir"></span></div>
      <button class="secondary" id="openFolderBtn" style="margin-top:12px">Open Folder</button>
    </section>

    <footer id="footer">Zefsnap • Powered by Zef Technology</footer>
  </main>

  <script>
    const state = { images: [], url: "", folder: null, latestUpdate: null };
    const $ = (id) => document.getElementById(id);

    function setThemeVars(theme) {
      const root = document.documentElement.style;
      root.setProperty("--accent", theme.accent);
      root.setProperty("--accent-hover", theme.accent_hover);
      root.setProperty("--near-black", theme.near_black);
      root.setProperty("--bg", theme.dark_bg);
      root.setProperty("--panel", theme.dark_panel);
      root.setProperty("--panel-2", theme.dark_panel_2);
      root.setProperty("--muted", theme.muted);
      root.setProperty("--border", theme.border);
    }

    async function boot() {
      const config = await window.pywebview.api.get_config();
      setThemeVars(config.theme);
      $("footer").textContent = config.footer;
      $("version").textContent = `v${config.version}`;
      if (config.assets.icon) $("favicon").href = config.assets.icon;
      if (config.assets.wordmark) {
        $("wordmark").src = config.assets.wordmark;
        $("wordmark").style.display = "block";
        $("brandFallback").style.display = "none";
      } else if (config.assets.smallWordmark) {
        $("wordmark").src = config.assets.smallWordmark;
        $("wordmark").style.display = "block";
        $("brandFallback").style.display = "none";
      } else {
        $("wordmark").style.display = "none";
        $("brandFallback").style.display = "block";
      }

      const update = await window.pywebview.api.check_update();
      if (update.available) {
        state.latestUpdate = update;
        $("updateText").textContent = `Update available — v${update.latest_version} (you're on v${update.current_version})`;
        $("updateBanner").style.display = "flex";
      }
    }

    function clearPreviousSession() {
      $("results").style.display = "none";
      $("completeBox").style.display = "none";
      $("progressBox").style.display = "none";
      $("progressFill").style.width = "0%";
      $("grid").innerHTML = "";
      $("productName").textContent = "";
      $("outputDir").textContent = "";
      $("openFolderBtn").dataset.path = "";
      $("statusText").textContent = "";
      state.images = [];
    }

    function scrollToProgress() {
      const progress = $("progressBox");
      progress.style.display = "block";
      progress.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function renderResults(result) {
      state.images = result.images || [];
      $("results").style.display = state.images.length ? "block" : "none";
      $("countBadge").textContent = `${state.images.length} images found`;
      $("grid").innerHTML = state.images.map((url, index) => `
        <article class="card">
          <label><input type="checkbox" class="imageCheck" data-index="${index}" checked /> #${index + 1}</label>
          <img src="${url}" alt="Product image ${index + 1}" loading="lazy" />
        </article>
      `).join("");
      $("statusText").textContent = result.error || "Images ready.";
      $("completeBox").style.display = "none";
    }

    window.zefsnapProgress = function(payload) {
      const data = typeof payload === "string" ? JSON.parse(payload) : payload;
      const percent = data.total ? Math.round((data.index / data.total) * 100) : 0;
      $("progressBox").style.display = "block";
      $("progressFill").style.width = `${percent}%`;
      $("statusText").textContent = `${data.status}: ${data.index}/${data.total} — ${data.file}`;
    };

    $("themeBtn").onclick = () => {
      const next = document.body.dataset.theme === "dark" ? "light" : "dark";
      document.body.dataset.theme = next;
      $("themeBtn").textContent = next === "dark" ? "Dark" : "Light";
    };

    $("folderBtn").onclick = async () => {
      const folder = await window.pywebview.api.choose_folder();
      if (folder) {
        state.folder = folder;
        $("folderPath").textContent = folder;
      }
    };

    $("pasteBtn").onclick = async () => {
      let text = "";
      try {
        text = await window.pywebview.api.paste_clipboard();
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
      state.url = $("url").value.trim();
      if (!state.url) return;
      clearPreviousSession();
      $("fetchBtn").disabled = true;
      $("statusText").textContent = "Fetching product page...";
      $("progressBox").style.display = "block";
      $("progressFill").style.width = "12%";
      scrollToProgress();
      const result = await window.pywebview.api.fetch_images(state.url, $("highRes").checked);
      renderResults(result);
      $("progressFill").style.width = result.images_found ? "100%" : "0%";
      $("fetchBtn").disabled = false;
      if (result.images_found) {
        $("results").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };

    $("selectAllBtn").onclick = () => {
      document.querySelectorAll(".imageCheck").forEach((box) => box.checked = true);
    };

    $("unselectAllBtn").onclick = () => {
      document.querySelectorAll(".imageCheck").forEach((box) => box.checked = false);
    };

    $("downloadBtn").onclick = async () => {
      const selected = [...document.querySelectorAll(".imageCheck")]
        .filter((box) => box.checked)
        .map((box) => state.images[Number(box.dataset.index)]);
      if (!selected.length) {
        $("statusText").textContent = "Select at least one image to download.";
        return;
      }
      $("downloadBtn").disabled = true;
      $("completeBox").style.display = "none";
      $("progressBox").style.display = "block";
      $("progressFill").style.width = "0%";
      const result = await window.pywebview.api.download_selected(state.url, selected, state.folder);
      $("downloadBtn").disabled = false;
      if (!result.error) {
        $("completeBox").style.display = "block";
        $("productName").textContent = result.product_name;
        $("outputDir").textContent = result.output_dir;
        $("openFolderBtn").dataset.path = result.output_dir;
        $("statusText").textContent = "Download complete.";
      } else {
        $("statusText").textContent = result.error;
      }
    };

    $("openFolderBtn").onclick = async () => {
      await window.pywebview.api.open_folder($("openFolderBtn").dataset.path);
    };

    $("updateBtn").onclick = async () => {
      if (!state.latestUpdate) return;
      $("updateText").textContent = "Downloading update...";
      await window.pywebview.api.update_now(state.latestUpdate.asset_url);
    };

    window.addEventListener("pywebviewready", boot);
  </script>
</body>
</html>"""


def run() -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("Install PyWebView first: pip install pywebview") from exc

    api = ZefsnapApi()
    icon = asset_path("logo images", "icon.ico")

    kwargs = {
        "title": APP_DISPLAY_NAME,
        "html": _html(),
        "js_api": api,
        "width": 1180,
        "height": 820,
        "min_size": (920, 680),
        "background_color": "#0B0D10",
    }
    if icon.exists():
        kwargs["icon"] = str(icon)

    try:
        window = webview.create_window(**kwargs)
    except TypeError:
        kwargs.pop("icon", None)
        window = webview.create_window(**kwargs)
    api.window = window
    webview.start(debug=False)


if __name__ == "__main__":
    run()
