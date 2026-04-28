#!/usr/bin/env python3
"""
Fetch articles from an Inoreader folder and output JSON.

Usage:
  python3 fetch.py --folder "Daily Briefing"
  python3 fetch.py --folder "Daily Briefing" --hours 48
  python3 fetch.py --folder "Daily Briefing" --out articles.json
  python3 fetch.py --list-folders

Output is a JSON array of normalized article objects written to stdout (default)
or to --out if specified.
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from auth_helpers import get_valid_tokens, auth_headers

load_dotenv(SCRIPT_DIR / ".env")

API_BASE = "https://www.inoreader.com/reader/api/0"


def resolve_folder_stream_id(tokens, folder_name):
    """Return the stream ID for a folder name, or None if not found."""
    resp = requests.get(
        f"{API_BASE}/tag/list",
        headers=auth_headers(tokens),
        params={"output": "json", "types": "1"},
        timeout=30,
    )
    resp.raise_for_status()
    _print_rate_limits(resp)

    for tag in resp.json().get("tags", []):
        tag_id = tag.get("id", "")
        if "/label/" in tag_id and tag_id.split("/label/")[-1] == folder_name:
            return tag_id

    return None


def list_folders(tokens):
    resp = requests.get(
        f"{API_BASE}/tag/list",
        headers=auth_headers(tokens),
        params={"output": "json", "types": "1", "counts": "1"},
        timeout=30,
    )
    resp.raise_for_status()
    for tag in resp.json().get("tags", []):
        tag_id = tag.get("id", "")
        if "/label/" in tag_id:
            name = tag_id.split("/label/")[-1]
            unread = tag.get("unread_count", "?")
            print(f"  {name!r}  (unread: {unread})")


def fetch_folder(tokens, stream_id, since_timestamp):
    """Fetch all articles from a stream since a Unix timestamp, paginating automatically."""
    articles = []
    params = {
        "output": "json",
        "n": 100,
        "ot": int(since_timestamp),
    }

    while True:
        url = f"{API_BASE}/stream/contents/{requests.utils.quote(stream_id, safe='')}"
        resp = requests.get(url, headers=auth_headers(tokens), params=params, timeout=30)
        resp.raise_for_status()
        _print_rate_limits(resp)

        data = resp.json()
        articles.extend(data.get("items", []))

        if "continuation" not in data:
            break
        params["c"] = data["continuation"]

    return articles


def _print_rate_limits(resp):
    z1_used = resp.headers.get("X-Reader-Zone1-Usage")
    z1_limit = resp.headers.get("X-Reader-Zone1-Limit")
    reset = resp.headers.get("X-Reader-Limits-Reset-After")
    if z1_used and z1_limit:
        print(f"[rate] Zone1: {z1_used}/{z1_limit} used, resets in {reset}s", file=sys.stderr)


def _clean_source_name(name):
    """Strip common RSS feed name suffixes."""
    noise = [
        r"\s*[-–—]\s*full rss.*",
        r"\s*[-–—]\s*rss feed.*",
        r"\s*[-–—]\s*all posts.*",
        r"\s*\(full rss\).*",
        r"\s*\(rss\).*",
    ]
    for pattern in noise:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
    return name.strip()


def _estimate_word_count(html_content):
    text = re.sub(r"<[^>]+>", " ", html_content)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text.split()) if text else 0


def normalize_article(item, folder_name=""):
    """Flatten a raw Inoreader item to a dict with the fields most pipelines need."""
    canonical = item.get("canonical", [{}])
    url = canonical[0].get("href", "") if canonical else ""

    ts_usec = item.get("timestampUsec")
    published = item.get("published")
    timestamp = int(ts_usec) / 1_000_000 if ts_usec else published

    return {
        "id": item.get("id", ""),
        "title": html.unescape(item.get("title", "")).strip(),
        "url": url,
        "author": item.get("author", ""),
        "published": timestamp,
        "published_iso": (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp else ""
        ),
        "source_feed": _clean_source_name(item.get("origin", {}).get("title", "")),
        "source_url": item.get("origin", {}).get("htmlUrl", ""),
        "folder": folder_name,
        "summary_html": item.get("summary", {}).get("content", ""),
        "word_count": _estimate_word_count(item.get("summary", {}).get("content", "")),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Inoreader articles as JSON")
    parser.add_argument("--folder", help="Folder name to fetch (case-sensitive)")
    parser.add_argument("--hours", type=float, default=24,
                        help="Lookback window in hours (default: 24)")
    parser.add_argument("--out", help="Write output to this file instead of stdout")
    parser.add_argument("--list-folders", action="store_true",
                        help="Print folder names and exit")
    args = parser.parse_args()

    tokens = get_valid_tokens()

    if args.list_folders:
        print("\nYour Inoreader folders:\n")
        list_folders(tokens)
        return

    if not args.folder:
        parser.error("--folder is required (or use --list-folders to see available folders)")

    stream_id = resolve_folder_stream_id(tokens, args.folder)
    if not stream_id:
        print(f"ERROR: Folder '{args.folder}' not found. Run --list-folders to see exact names.",
              file=sys.stderr)
        sys.exit(1)

    since = time.time() - (args.hours * 3600)
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"Fetching '{args.folder}' since {since_iso} ({args.hours}h lookback)...",
          file=sys.stderr)

    raw_items = fetch_folder(tokens, stream_id, since)

    seen_urls = set()
    articles = []
    for item in raw_items:
        article = normalize_article(item, args.folder)
        if not article["url"] or article["url"] in seen_urls:
            continue
        if not article["title"]:
            continue
        seen_urls.add(article["url"])
        articles.append(article)

    articles.sort(key=lambda a: a["published"] or 0, reverse=True)

    print(f"Fetched {len(articles)} articles.", file=sys.stderr)

    output = json.dumps(articles, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output)
        print(f"Saved to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
