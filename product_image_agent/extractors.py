from __future__ import annotations

import html as html_lib
import json
import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, unquote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def normalize_url(url: str, base: str | None = None) -> str:
    url = html_lib.unescape(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    elif base and not url.startswith(("http://", "https://")):
        url = urljoin(base, url)
    return url


def unique_preserve_order(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def clean_image_url(url: str) -> str:
    return html_lib.unescape(url).strip().strip('"\'')


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] or "product"
    return re.sub(r"\.html?$", "", slug, flags=re.I)


def prettify_slug(slug: str) -> str:
    words = re.sub(r"[_\-]+", " ", slug).strip()
    return words.title() if words else "Product"


def color_from_query(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    raw = query.get("color", [None])[0]
    if not raw:
        return None
    return unquote(raw).replace("-", " ").replace("_", " ").title()


def _json_items(data: object) -> Iterable[dict]:
    if isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _json_items(item)
    elif isinstance(data, list):
        for item in data:
            yield from _json_items(item)


def _is_product_type(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() == "product"
    if isinstance(value, list):
        return any(_is_product_type(item) for item in value)
    return False


def _image_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("url", "contentUrl", "src"):
            found = value.get(key)
            if isinstance(found, str):
                yield found
        nested = value.get("image")
        if nested is not None:
            yield from _image_values(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _image_values(item)


def find_json_ld_images(html: str, page_url: str) -> list[str]:
    urls: list[str] = []
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.DOTALL,
    ):
        try:
            data = json.loads(html_lib.unescape(block).strip())
        except json.JSONDecodeError:
            continue
        for item in _json_items(data):
            if not _is_product_type(item.get("@type")):
                continue
            urls.extend(normalize_url(u, page_url) for u in _image_values(item.get("image")))
    return unique_preserve_order(urls)


def request_ok(url: str, timeout: int = 5) -> bool:
    for method in ("HEAD", "GET"):
        request = Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout) as response:
                return 200 <= response.status < 400
        except HTTPError as exc:
            if exc.code == 405 and method == "HEAD":
                continue
            return False
        except (OSError, URLError, ValueError):
            return False
    return False


def _upgrade_query(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    query = parse_qs(parsed.query, keep_blank_values=True)
    remove_keys = {
        "size",
        "width",
        "height",
        "fit",
        "crop",
        "thumbnail",
        "thumb",
        "resize",
    }
    for key in list(query):
        lower = key.lower()
        if lower in remove_keys:
            query.pop(key, None)
        elif lower in {"w", "h"}:
            query[key] = ["2000"]
        elif lower in {"q", "quality"}:
            query[key] = ["90"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _upgrade_path(url: str) -> list[str]:
    parsed = urlparse(url)
    path = parsed.path
    candidates: list[str] = []

    shopify_suffix = re.compile(
        r"(_(?:pico|icon|thumb|small|compact|medium|large|grande|master|"
        r"\d+x\d*|\d*x\d+|x\d+))(?=\.(?:jpe?g|png|webp|gif)$)",
        re.I,
    )
    if shopify_suffix.search(path):
        stripped = shopify_suffix.sub("", path)
        candidates.append(urlunparse(parsed._replace(path=stripped)))
        candidates.append(urlunparse(parsed._replace(path=shopify_suffix.sub("_2048x2048", path))))

    woo_original = re.sub(r"-\d{2,5}x\d{2,5}(?=\.(?:jpe?g|png|webp)$)", "", path, flags=re.I)
    if woo_original != path:
        candidates.append(urlunparse(parsed._replace(path=woo_original)))

    common_thumb = re.sub(
        r"([/_-])(?:thumb|thumbnail|small|medium|tiny|std)(?=\.(?:jpe?g|png|webp)$)",
        r"\1large",
        path,
        flags=re.I,
    )
    if common_thumb != path:
        candidates.append(urlunparse(parsed._replace(path=common_thumb)))

    return candidates


def resolve_highest_resolution(url: str, base: str | None = None, verify: bool = True) -> str:
    original = normalize_url(clean_image_url(url), base)
    if not original or original.startswith("data:"):
        return original

    candidates = unique_preserve_order([*_upgrade_path(original), _upgrade_query(original)])
    for candidate in candidates:
        if candidate != original and (not verify or request_ok(candidate)):
            return candidate
    return original


def parse_srcset(srcset: str, base: str | None = None) -> str | None:
    best_url: str | None = None
    best_score = -1.0
    for item in srcset.split(","):
        parts = item.strip().split()
        if not parts:
            continue
        url = normalize_url(parts[0], base)
        score = 1.0
        if len(parts) > 1:
            descriptor = parts[-1].lower()
            if descriptor.endswith("w"):
                try:
                    score = float(descriptor[:-1])
                except ValueError:
                    score = 1.0
            elif descriptor.endswith("x"):
                try:
                    score = float(descriptor[:-1]) * 1000
                except ValueError:
                    score = 1.0
        if score > best_score:
            best_score = score
            best_url = url
    return best_url


def image_is_noise(url: str) -> bool:
    name = urlparse(url).path.rsplit("/", 1)[-1].lower()
    return any(
        token in name
        for token in (
            "favicon",
            "sprite",
            "logo",
            "icon",
            "badge",
            "payment",
            "placeholder",
            "loader",
            ".svg",
        )
    )


def _attrs_from_tag(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in re.findall(
        r"([:\w\-]+)\s*=\s*([\"'])(.*?)\2",
        tag,
        flags=re.I | re.DOTALL,
    ):
        attrs[key.lower()] = html_lib.unescape(value)
    return attrs


class ProductImageHTMLParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.meta_images: list[str] = []
        self.srcset_images: list[str] = []
        self.gallery_attr_images: list[str] = []
        self.gallery_container_images: list[str] = []
        self._gallery_depth = 0

    def handle_starttag(self, tag: str, attrs_raw: list[tuple[str, str | None]]) -> None:
        attrs = {k.lower(): (v or "") for k, v in attrs_raw}
        class_id = f"{attrs.get('class', '')} {attrs.get('id', '')}".lower()
        is_gallery = any(
            token in class_id
            for token in ("gallery", "product-image", "product__media", "pdp-image", "carousel")
        )
        if is_gallery:
            self._gallery_depth += 1

        if tag.lower() == "meta":
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop in {"og:image", "og:image:secure_url", "twitter:image"}:
                content = attrs.get("content")
                if content:
                    self.meta_images.append(normalize_url(content, self.page_url))

        if tag.lower() in {"img", "source"}:
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            if srcset:
                best = parse_srcset(srcset, self.page_url)
                if best:
                    self.srcset_images.append(best)

            for attr in ("data-zoom-image", "data-image", "data-large_image", "data-src", "data-original"):
                value = attrs.get(attr)
                if value:
                    self.gallery_attr_images.append(normalize_url(value, self.page_url))

            src = attrs.get("src") or attrs.get("data-src")
            if src and self._gallery_depth:
                width = attrs.get("width")
                height = attrs.get("height")
                if not self._tiny_dimensions(width, height):
                    self.gallery_container_images.append(normalize_url(src, self.page_url))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"div", "section", "ul", "ol", "figure"} and self._gallery_depth:
            self._gallery_depth -= 1

    @staticmethod
    def _tiny_dimensions(width: str | None, height: str | None) -> bool:
        try:
            return bool(width and height and int(width) < 120 and int(height) < 120)
        except ValueError:
            return False


def parse_html_images(html: str, page_url: str) -> ProductImageHTMLParser:
    parser = ProductImageHTMLParser(page_url)
    parser.feed(html)
    return parser


class BaseExtractor(ABC):
    domains: tuple[str, ...] = ()

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)

    @abstractmethod
    def extract(self, html: str, page_url: str, *, high_res: bool = True) -> list[str]:
        raise NotImplementedError

    def _finish(self, urls: Iterable[str], page_url: str, *, high_res: bool) -> list[str]:
        filtered = [normalize_url(u, page_url) for u in urls if u and not image_is_noise(u)]
        if high_res:
            filtered = [resolve_highest_resolution(u, page_url) for u in filtered]
        return unique_preserve_order(filtered)


class QuinceExtractor(BaseExtractor):
    domains = ("quince.com",)

    def extract(self, html: str, page_url: str, *, high_res: bool = True) -> list[str]:
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            flags=re.DOTALL,
        )
        if not match:
            return []

        data = json.loads(match.group(1))
        product = (
            data.get("props", {})
            .get("pageProps", {})
            .get("pageData", {})
            .get("context", {})
            .get("pageDataJson", {})
            .get("product", {})
        )
        images = product.get("images") or []
        selected_color = color_from_query(page_url)

        urls: list[str] = []
        for entry in images:
            if not isinstance(entry, dict):
                continue
            options = entry.get("options") or []
            color_values: list[str] = []
            for option in options:
                if option.get("name", "").lower() == "color":
                    color_values.extend(option.get("values") or [])

            if selected_color and color_values and selected_color not in color_values:
                continue

            image = entry.get("image") or {}
            raw_url = image.get("url") or ""
            if not raw_url:
                continue
            urls.append(self._to_high_res(raw_url, html))

        return self._finish(urls, page_url, high_res=high_res)

    def _to_high_res(self, raw_url: str, html: str) -> str:
        raw_url = normalize_url(raw_url)
        filename = raw_url.rsplit("/", 1)[-1].split("?")[0]
        quince_match = re.search(
            rf"https://images\.quince\.com/[^\"'\s<>\\]+{re.escape(filename)}[^\"'\s<>\\]*",
            html.replace("&amp;", "&"),
        )
        if quince_match:
            candidate = quince_match.group(0)
            if "fm=avif" not in candidate and "fm=webp" not in candidate:
                return candidate

        ctf_match = re.search(r"ctfassets\.net/[^/]+/(.+)$", raw_url)
        if ctf_match:
            return (
                f"https://images.quince.com/{ctf_match.group(1)}"
                "?w=1600&q=50&h=2000&reqOrigin=website-ssr"
            )
        return raw_url


RELATED_PRODUCT_MARKERS = (
    "you may also like",
    "related products",
    "customers also viewed",
    "similar products",
    "recently viewed",
    "recommended for you",
)


def _main_product_html(html: str) -> str:
    lower = html.lower()
    end = len(html)
    for marker in RELATED_PRODUCT_MARKERS:
        idx = lower.find(marker)
        if idx > 0:
            end = min(end, idx)

    start = lower.find("productview")
    if start == -1:
        start = lower.find("magiczoom")
    if start == -1:
        start = 0
    return html[start:end]


class BigCommerceExtractor(BaseExtractor):
    """Fjackets, Angel Jackets, and similar BigCommerce + MagicZoom stores."""

    domains = ("fjackets.com", "angeljackets.com")

    def extract(self, html: str, page_url: str, *, high_res: bool = True) -> list[str]:
        gallery_html = _main_product_html(html)
        urls: list[str] = []

        for pattern in [
            r'data-image=["\']([^"\']+product_images[^"\']+)["\']',
            r'data-zoom-image=["\']([^"\']+product_images[^"\']+)["\']',
            r'href=["\']([^"\']+product_images/[^"\']+_zoom\.(?:webp|jpg|jpeg|png))["\']',
            r'https?://[^"\']+product_images/[^"\']+_zoom\.(?:webp|jpg|jpeg|png)',
            r'https?://[^"\']+product_images/[^"\']+_std\.(?:webp|jpg|jpeg|png)',
        ]:
            for match in re.findall(pattern, gallery_html, flags=re.I):
                value = match if isinstance(match, str) else match
                if "%%" in value or image_is_noise(value):
                    continue
                urls.append(value)

        if urls:
            zoom_urls = [u for u in urls if "_zoom." in u.lower()]
            if zoom_urls:
                urls = zoom_urls
            return self._finish(urls, page_url, high_res=high_res)

        return self._from_json_ld(html, page_url, high_res=high_res)

    def _from_json_ld(self, html: str, page_url: str, *, high_res: bool) -> list[str]:
        return self._finish(find_json_ld_images(html, page_url), page_url, high_res=high_res)


class GenericExtractor(BaseExtractor):
    domains = ()

    def matches(self, url: str) -> bool:
        return True

    def extract(self, html: str, page_url: str, *, high_res: bool = True) -> list[str]:
        parsed = parse_html_images(html, page_url)

        priority_groups = [
            find_json_ld_images(html, page_url),
            parsed.meta_images,
            parsed.srcset_images,
            self._regex_gallery_urls(html, page_url),
            parsed.gallery_attr_images,
            parsed.gallery_container_images,
        ]

        urls: list[str] = []
        for group in priority_groups:
            urls.extend(group)

        return self._finish(urls, page_url, high_res=high_res)

    def _regex_gallery_urls(self, html: str, page_url: str) -> list[str]:
        urls: list[str] = []
        patterns = [
            r'https?://[^"\'\s<>]+product_images/[^"\'\s<>]+_zoom\.(?:webp|jpg|jpeg|png)',
            r'(?:data-zoom-image|data-image|data-large_image|data-src)=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, html, flags=re.I):
                urls.append(normalize_url(match, page_url))
        return urls


EXTRACTORS: list[BaseExtractor] = [
    QuinceExtractor(),
    BigCommerceExtractor(),
    GenericExtractor(),
]


def get_extractor(url: str) -> BaseExtractor:
    for extractor in EXTRACTORS:
        if extractor.matches(url):
            return extractor
    return GenericExtractor()


def extract_product_images(html: str, page_url: str, *, high_res: bool = True) -> list[str]:
    extractor = get_extractor(page_url)
    urls = extractor.extract(html, page_url, high_res=high_res)
    if urls:
        return urls
    return GenericExtractor().extract(html, page_url, high_res=high_res)
