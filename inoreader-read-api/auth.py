#!/usr/bin/env python3
"""
Inoreader OAuth setup and token management.

First run:    python3 auth.py
              Follow the printed URL, authorize in browser, paste back the redirect URL.

Later runs:   python3 auth.py --refresh        Force token refresh
              python3 auth.py --list-folders   Show your Inoreader folders and unread counts

Tokens are saved to .tokens.json (gitignored, chmod 600).
"""

import argparse
import os
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from auth_helpers import (
    load_tokens, save_tokens, is_expired,
    refresh_tokens, get_valid_tokens, auth_headers,
)

load_dotenv(SCRIPT_DIR / ".env")

AUTH_URL = "https://www.inoreader.com/oauth2/auth"
TOKEN_URL = "https://www.inoreader.com/oauth2/token"
API_BASE = "https://www.inoreader.com/reader/api/0"
REDIRECT_URI = "http://localhost"


def get_credentials():
    client_id = os.getenv("INOREADER_CLIENT_ID")
    client_secret = os.getenv("INOREADER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: Set INOREADER_CLIENT_ID and INOREADER_CLIENT_SECRET in your .env file.")
        print("Get these by registering an app at:")
        print("  https://www.inoreader.com/preferences/profile/general")
        sys.exit(1)
    return client_id, client_secret


def do_initial_auth():
    client_id, client_secret = get_credentials()
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "read",
        "state": state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("\n=== Inoreader OAuth Setup ===")
    print("\n1. Open this URL in your browser:\n")
    print(f"   {url}\n")
    print("2. Authorize the app.")
    print("3. You'll be redirected to a localhost URL that won't load — that's expected.")
    print("4. Copy the full URL from your browser's address bar and paste it here.\n")

    redirect = input("Paste redirect URL: ").strip()
    parsed = urllib.parse.urlparse(redirect)
    query = urllib.parse.parse_qs(parsed.query)
    code = query.get("code", [None])[0]
    returned_state = query.get("state", [None])[0]

    if parsed.scheme != "http" or parsed.hostname != "localhost":
        print("ERROR: Redirect URL must start with http://localhost.")
        sys.exit(1)
    if returned_state != state:
        print("ERROR: OAuth state mismatch. Try the authorization flow again.")
        sys.exit(1)
    if not code:
        print("ERROR: Could not extract 'code' from that URL.")
        sys.exit(1)

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": time.time() + data["expires_in"],
    }
    save_tokens(tokens)
    print("\nAuthorization successful! Tokens saved to .tokens.json")


def list_folders():
    tokens = get_valid_tokens()
    resp = requests.get(
        f"{API_BASE}/tag/list",
        headers=auth_headers(tokens),
        params={"output": "json", "types": "1", "counts": "1"},
        timeout=30,
    )
    resp.raise_for_status()
    tags = resp.json().get("tags", [])

    print("\nYour Inoreader folders:\n")
    for tag in tags:
        tag_id = tag.get("id", "")
        if "/label/" in tag_id:
            folder_name = tag_id.split("/label/")[-1]
            unread = tag.get("unread_count", "?")
            print(f"  {folder_name!r}  (unread: {unread})")
    print()
    print("Use the exact folder name (case-sensitive) when calling fetch.py.")


def main():
    parser = argparse.ArgumentParser(description="Inoreader OAuth setup and token management")
    parser.add_argument("--refresh", action="store_true", help="Force token refresh")
    parser.add_argument("--list-folders", action="store_true", help="List folders and unread counts")
    args = parser.parse_args()

    if args.list_folders:
        list_folders()
    elif args.refresh:
        tokens = load_tokens()
        if not tokens:
            print("No tokens found. Run without --refresh first.")
            sys.exit(1)
        refresh_tokens(tokens)
        print("Token refreshed.")
    else:
        existing = load_tokens()
        if existing and not is_expired(existing):
            print("Already authorized. Use --refresh to force a new token or --list-folders to inspect your account.")
        else:
            do_initial_auth()


if __name__ == "__main__":
    main()
