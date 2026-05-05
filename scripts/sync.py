#!/usr/bin/env python3
import sys
import time
from pathlib import Path

import requests
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
UPSTREAM_FILE = BASE_DIR / "upstream.yml"
DIST_DIR = BASE_DIR / "dist"

DIST_DIR.mkdir(exist_ok=True)


HTML_MARKERS = (
    "<html",
    "<!doctype html",
    "404 not found",
    "403 forbidden",
    "cloudflare",
)


def load_config():
    if not UPSTREAM_FILE.exists():
        print(f"Missing config file: {UPSTREAM_FILE}")
        sys.exit(1)

    with UPSTREAM_FILE.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "resources" not in config:
        print("No resources found in upstream.yml")
        sys.exit(1)

    return config


def looks_bad(text: str):
    stripped = text.strip()
    lower_text = stripped.lower()

    if len(stripped) < 10:
        return True, "response too small"

    if any(marker in lower_text for marker in HTML_MARKERS):
        return True, "response looks like HTML/error page"

    return False, ""


def fetch_resource(url: str):
    print(f"Fetching: {url}")

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "surge-rules-mirror/1.0"
            },
        )
        response.raise_for_status()
    except Exception as e:
        print(f"  ERROR: failed to fetch {url}: {e}")
        return None

    text = response.text.replace("\r\n", "\n").replace("\r", "\n")

    bad, reason = looks_bad(text)
    if bad:
        print(f"  ERROR: bad response from {url}: {reason}")
        return None

    return text.strip() + "\n"


def write_dist(filename: str, content: str):
    dist_file = DIST_DIR / filename

    old_content = None
    if dist_file.exists():
        old_content = dist_file.read_text(encoding="utf-8")

    header = (
        "# Mirrored by GitHub Actions\n"
        f"# Updated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        f"# Source file: {filename}\n"
        "\n"
    )

    final_content = header + content

    if old_content == final_content:
        print(f"No change: {dist_file}")
        return False

    dist_file.write_text(final_content, encoding="utf-8")
    print(f"Updated: {dist_file}")
    return True


def main():
    config = load_config()
    resources = config.get("resources", {})

    any_updated = False

    for filename, item in resources.items():
        print(f"\n=== Mirroring: {filename} ===")

        if isinstance(item, str):
            source = item
        elif isinstance(item, dict):
            source = item.get("source")
        else:
            print(f"ERROR: invalid config for {filename}, skip")
            continue

        if not source:
            print(f"ERROR: missing source for {filename}, skip")
            continue

        content = fetch_resource(source)

        if content is None:
            print(f"Skip writing {filename}; keep old version if it exists.")
            continue

        updated = write_dist(filename, content)
        any_updated = any_updated or updated

    if any_updated:
        print("\nDone: some resources updated.")
    else:
        print("\nDone: no resource changed.")


if __name__ == "__main__":
    main()
