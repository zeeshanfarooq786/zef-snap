from __future__ import annotations

import argparse
import json

from .downloader import download_product_images


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download all product images from an e-commerce product page.",
    )
    parser.add_argument("url", help="Product detail page URL")
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory (default: downloads/<product-slug>)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print image URLs without downloading",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON",
    )
    parser.add_argument(
        "--js",
        action="store_true",
        help="Use Playwright only if static HTML extraction finds zero images",
    )
    parser.add_argument(
        "--no-high-res",
        action="store_true",
        help="Disable URL high-resolution upgrades",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = download_product_images(
        args.url,
        output_dir=args.output,
        dry_run=args.dry_run,
        use_js=args.js,
        high_res=not args.no_high_res,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["error"]:
            print(f"Error: {result['error']}")
            return 1
        print(f"Product: {result['url']}")
        print(f"Images found: {result['images_found']}")
        if result.get("used_js"):
            print("Rendered with Playwright fallback: yes")
        if args.dry_run:
            print("Dry run - image URLs:")
            for item in result["downloaded"]:
                print(f"  {item['url']}")
        else:
            print(f"Saved to: {result['output_dir']}")
            for item in result["downloaded"]:
                print(f"  {item['file']}")

    return 0 if not result["error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
