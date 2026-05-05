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


def load_config():
    if not UPSTREAM_FILE.exists():
        print(f"Missing config file: {UPSTREAM_FILE}")
        sys.exit(1)

    with UPSTREAM_FILE.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "resources" not in config:
        print("No resources found in upstream.yml")
        sys.exit(1)

    if not isinstance(config["resources"], dict):
        print("Invalid upstream.yml: resources must be a mapping/dict")
        sys.exit(1)

    return config


def looks_bad(text: str):
    """
    判断响应内容是否明显不是规则文件。

    注意：
    不要用 'cloudflare' 这种关键词做全局判断。
    很多正常规则里会包含 cloudflare.com / cloudflare-dns.com，
    否则会误判 AI.list / CDN-DomainSet.list 等规则。
    """
    stripped = text.strip()

    if not stripped:
        return True, "empty response"

    head = stripped.lower()[:800].lstrip()

    html_markers = (
        "<!doctype html",
        "<html",
        "<head",
        "<title>",
        "</html>",
    )

    if any(marker in head for marker in html_markers):
        return True, "response looks like HTML/error page"

    plain_error_prefixes = (
        "404 not found",
        "403 forbidden",
        "401 unauthorized",
        "400 bad request",
        "500 internal server error",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
    )

    if head.startswith(plain_error_prefixes):
        return True, "response looks like HTTP error page"

    return False, ""


def fetch_resource(url: str):
    print(f"Fetching repr: {url!r}")
    print(f"Fetching: {url}")

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "surge-rules-mirror/1.0"
            },
        )

        print(f"  HTTP status: {response.status_code}")
        response.raise_for_status()

    except Exception as e:
        print(f"  ERROR: failed to fetch {url!r}: {e}")
        return None

    text = response.text.replace("\r\n", "\n").replace("\r", "\n")
    byte_len = len(text.encode("utf-8"))

    print(f"  Downloaded: {byte_len} bytes")

    bad, reason = looks_bad(text)
    if bad:
        print(f"  ERROR: bad response from {url!r}: {reason}")
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
        print(f"  No change: {dist_file}")
        return "unchanged"

    dist_file.write_text(final_content, encoding="utf-8")
    print(f"  Updated: {dist_file}")
    return "updated"


def normalize_source(filename: str, item):
    if isinstance(item, str):
        source = item
    elif isinstance(item, dict):
        source = item.get("source")
    else:
        print(f"  ERROR: invalid config for {filename}, skip")
        return None

    if not source:
        print(f"  ERROR: missing source for {filename}, skip")
        return None

    source = str(source).strip()

    if source.startswith(("http://", "https://")) and source.endswith(":"):
        print(f"  WARN: source URL has trailing colon, auto-fixing: {source!r}")
        source = source[:-1]

    return source


def main():
    config = load_config()
    resources = config.get("resources", {})

    updated = []
    unchanged = []
    skipped = []

    for filename, item in resources.items():
        print(f"\n=== Mirroring: {filename} ===")

        source = normalize_source(filename, item)
        if source is None:
            skipped.append(filename)
            continue

        print(f"  Source after cleanup: {source!r}")

        content = fetch_resource(source)

        if content is None:
            print(f"  Skip writing {filename}; keep old version if it exists.")
            skipped.append(filename)
            continue

        result = write_dist(filename, content)

        if result == "updated":
            updated.append(filename)
        elif result == "unchanged":
            unchanged.append(filename)
        else:
            skipped.append(filename)

    print("\n=== Sync Summary ===")
    print(f"Updated:   {len(updated)}")
    print(f"Unchanged: {len(unchanged)}")
    print(f"Skipped:   {len(skipped)}")

    if updated:
        print("\nUpdated files:")
        for name in updated:
            print(f"  - {name}")

    if skipped:
        print("\nSkipped files:")
        for name in skipped:
            print(f"  - {name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
