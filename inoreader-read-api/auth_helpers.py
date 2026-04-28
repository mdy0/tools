"""Shared token loading and refresh logic for Inoreader API scripts."""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent

load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / ".tokens.json"
TOKEN_URL = "https://www.inoreader.com/oauth2/token"


def load_tokens():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def save_tokens(tokens):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    os.chmod(TOKEN_FILE, 0o600)


def is_expired(tokens):
    return time.time() >= tokens.get("expires_at", 0) - 60


def refresh_tokens(tokens):
    client_id = os.getenv("INOREADER_CLIENT_ID")
    client_secret = os.getenv("INOREADER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: INOREADER_CLIENT_ID and INOREADER_CLIENT_SECRET must be set in .env")
        sys.exit(1)
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    tokens["access_token"] = data["access_token"]
    tokens["expires_at"] = time.time() + data["expires_in"]
    if "refresh_token" in data:
        tokens["refresh_token"] = data["refresh_token"]
    save_tokens(tokens)
    return tokens


def get_valid_tokens():
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run: python3 auth.py")
        sys.exit(1)
    if is_expired(tokens):
        print("Access token expired, refreshing...")
        tokens = refresh_tokens(tokens)
    return tokens


def auth_headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}
