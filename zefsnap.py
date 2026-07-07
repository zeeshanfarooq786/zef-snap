#!/usr/bin/env python3
"""Launch the Zefsnap desktop app."""

import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if "--verify-ssl" in sys.argv:
        from product_image_agent.net import verify_ssl_connectivity

        verify_file = Path(tempfile.gettempdir()) / "zefsnap_ssl_verify.txt"
        try:
            result = verify_ssl_connectivity()
            verify_file.write_text(result, encoding="utf-8")
        except Exception as exc:
            verify_file.write_text(f"ERROR: {exc}", encoding="utf-8")
            raise
        finally:
            os._exit(0)

    if "--verify-fetch" in sys.argv:
        from product_image_agent.downloader import discover_product_images

        verify_file = Path(tempfile.gettempdir()) / "zefsnap_fetch_verify.txt"
        test_url = (
            "https://www.fjackets.com/buy/womens-shirt-collar-maroon-leather-jacket.html"
        )
        try:
            result = discover_product_images(test_url, use_js=False, high_res=True)
            image_count = len(result.get("images") or [])
            verify_file.write_text(f"images={image_count}", encoding="utf-8")
        except Exception as exc:
            verify_file.write_text(f"ERROR: {exc}", encoding="utf-8")
            raise
        finally:
            os._exit(0)

    from product_image_agent.gui import run

    run()


if __name__ == "__main__":
    main()
