# inoreader-read-api

A Python integration for authenticating with the Inoreader API and fetching articles from your subscriptions. Uses OAuth 2.0 with a local redirect flow — no server required. Tokens are stored locally and refreshed automatically on subsequent runs.

**What it does**: authorizes against Inoreader once in a browser, saves the token pair locally, and gives you paginated JSON access to any of your folders and their articles. It does not write to your account or modify read state.

**What it is not**: a full Inoreader client. Write operations (marking articles as read, managing subscriptions) are possible via the same API but not implemented here.

> This tool reflects the Inoreader API as of April 2026. The API is stable but the developer portal UI may change; the steps below describe what to look for rather than pixel-exact navigation.

---

## One-time human setup

These steps require a human with an Inoreader Pro account. They only need to be done once.

### Prerequisites

**Inoreader Pro subscription required.** Inoreader's policy reserves free API access for developers building publicly available apps on platforms where Inoreader has no native presence. For personal pipelines and private tools, a Pro subscription is required. A free account cannot register API applications or make authenticated API calls. Confirm your account tier before proceeding.

### 1. Register a developer application

1. Log in to Inoreader and go to **Preferences → Profile** (gear icon → your profile page).
2. Scroll the left sidebar to the **Developer API** section near the bottom.
3. Click **New application**.
4. Fill in the fields:
   - **Application name**: anything descriptive (e.g., `My Feed Pipeline`)
   - **Application URL**: any valid URL — your personal site or `https://github.com` works fine; Inoreader does not verify it
   - **Platform**: `MacOS` (or your actual platform)
   - **Redirect URI**: `http://localhost` — does not need to be a running server
   - **OAuth scope**: `Read`
5. Save. Inoreader displays an **App ID** (client ID) and **App Key** (client secret). Copy both.

### 2. Set up credentials

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and fill in both values:

```
INOREADER_CLIENT_ID=your_app_id_here
INOREADER_CLIENT_SECRET=your_app_key_here
```

`.env` is gitignored and must never be committed.

### 3. Run the authorization flow

Run this in an **interactive terminal** (not via cron or an AI agent — it requires keyboard input):

```bash
python3 auth.py
```

The script prints an authorization URL. Open it in a browser. After you authorize the app, the browser redirects to a localhost URL that fails to load — that's expected. Copy the full URL from the address bar and paste it back into the terminal.

Tokens are saved to `.tokens.json` (`chmod 600`).

---

## Deployment options

**User-level (shared across projects)** — clone this repo somewhere stable and add the directory to your PATH or create an alias. All projects share one `.env` and one `.tokens.json` in this directory.

- Use this when: multiple projects consume the same Inoreader account and you don't want to repeat setup

**Project-level (self-contained)** — copy `auth.py`, `fetch.py`, and `auth_helpers.py` into your project's scripts directory. Keep `.env` and `.tokens.json` local to that project.

- Use this when: you want the project to be fully self-contained or the Inoreader credentials differ per project

---

## Usage

```bash
# List your folders and unread counts
python3 auth.py --list-folders

# Fetch articles from a folder (last 24h, saves to data/YYYY-MM-DD.json)
python3 fetch.py --folder "Daily Briefing"

# Fetch with a custom lookback window
python3 fetch.py --folder "Daily Briefing" --hours 48

# Write output to a specific file
python3 fetch.py --folder "Daily Briefing" --out articles.json

# Write to stdout for piping
python3 fetch.py --folder "Daily Briefing" --out -

# Force a token refresh
python3 auth.py --refresh
```

By default, output is saved to `data/YYYY-MM-DD.json` in the current directory (created if it doesn't exist). Rate limit diagnostics are printed to stderr. Use `--out -` to write JSON to stdout for piping:

```bash
python3 fetch.py --folder "Daily Briefing" --out - | jq '.[].title'
```

---

## Integration

### From Python

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("path/to/inoreader-read-api")))

from auth_helpers import get_valid_tokens, auth_headers
import requests

tokens = get_valid_tokens()
resp = requests.get(
    "https://www.inoreader.com/reader/api/0/tag/list",
    headers=auth_headers(tokens),
    params={"output": "json", "types": "1", "counts": "1"},
    timeout=30,
)
```

Or import `normalize_article` from `fetch.py` to reuse the article normalization logic:

```python
from fetch import normalize_article

raw_item = { ... }  # from Inoreader stream/contents response
article = normalize_article(raw_item, folder_name="Daily Briefing")
# article["title"], article["url"], article["published_iso"], etc.
```

### From shell

```bash
# Pipe into another tool
python3 fetch.py --folder "News" --hours 24 --out - | python3 my_pipeline.py

# Save to a specific path and process later
python3 fetch.py --folder "News" --out /tmp/articles.json
jq '.[].url' /tmp/articles.json
```

---

## Credentials reference

| Credential | Where it comes from | Where it's stored |
|---|---|---|
| `INOREADER_CLIENT_ID` | Inoreader developer portal (App ID) | `.env` |
| `INOREADER_CLIENT_SECRET` | Inoreader developer portal (App Key) | `.env` |
| `access_token` | OAuth exchange, auto-refreshed | `.tokens.json` |
| `refresh_token` | OAuth exchange, used to get new access tokens | `.tokens.json` |

`.env` holds static app credentials. `.tokens.json` holds live session tokens. Both are gitignored and should be `chmod 600`.

---

## Token lifecycle

Access tokens expire after approximately one hour. `auth_helpers.py` handles this automatically: every call to `get_valid_tokens()` checks expiry and silently refreshes before returning.

To force a refresh manually: `python3 auth.py --refresh`

If the refresh token itself expires or is revoked (e.g., you revoke the app in Inoreader's connected-apps settings), re-run the full `python3 auth.py` flow without flags.

---

## Rate limits

Zone-based daily limits. As of April 2026:

| Zone | Covers | Default limit |
|---|---|---|
| Zone 1 | Read operations | 100 requests/day |
| Zone 2 | Write operations | 100 requests/day |

Response headers on every API call show current usage: `X-Reader-Zone1-Usage`, `X-Reader-Zone1-Limit`, `X-Reader-Limits-Reset-After`. These are printed to stderr on each request.

For a pipeline that fetches one folder at 100 articles, that's 2 Zone 1 requests minimum (1 for `tag/list` + 1 for stream contents, assuming no pagination). Fits easily within the daily limit for a once-a-day run.

---

## For AI coding agents

### Prerequisites (human must do these first)

Before the agent can proceed, a human must:

1. Confirm they have an active **Inoreader Pro** subscription.
2. Register a developer application in the Inoreader preferences and save the **App ID** and **App Key**.
3. Create `.env` with `INOREADER_CLIENT_ID` and `INOREADER_CLIENT_SECRET` populated.
4. Run `python3 auth.py` in an interactive terminal to complete the browser-based OAuth flow.

An AI coding agent cannot log in to Inoreader, navigate the developer portal, or complete the browser-based OAuth flow. The initial authorization (step 4) requires a live terminal with keyboard input.

### Setup steps

**Step 1 — Confirm `.env` is populated:**

```bash
grep -q INOREADER_CLIENT_ID .env && echo "Found" || echo "Missing"
```

If missing, ask the human to create it with both credential keys before continuing.

**Step 2 — Ask the human to run the authorization flow** in their own terminal (not via the agent's Bash tool — it calls `input()`):

```bash
python3 auth.py
```

They should open the printed URL, authorize, copy the redirect URL from the address bar, paste it back, and confirm they see `Authorization successful!`.

**Step 3 — Verify the connection** (this call is non-interactive and can be run by the agent):

```bash
python3 auth.py --list-folders
```

Confirms `.tokens.json` was written and the API is reachable.

**Step 4 — Test a fetch:**

```bash
python3 fetch.py --folder "FolderNameHere" --hours 24
```

Use the exact folder name from `--list-folders` output. Confirm you see a JSON array of articles.

### What to watch out for

- **Pro subscription required for private use.** A free account cannot register apps or call the API.
- **The OAuth flow requires a human.** `auth.py` calls `input()` to receive the redirect URL. Running it via cron, CI, or an AI agent's Bash tool will raise `EOFError`. Always run it in a live terminal.
- **Never commit credentials.** `.env` and `.tokens.json` are both gitignored. Both should be `chmod 600`.
- **`http://localhost` as the redirect URI is intentional.** The browser shows an error page — that's expected. The code is in the URL bar. Copy the full URL.
- **Folder names are case-sensitive.** Use the exact string from `--list-folders` output. Do not paraphrase.
- **`timestampUsec` is in microseconds.** The normalization in `fetch.py` divides by `1_000_000` to get Unix seconds. Raw items from the API need this conversion before any date arithmetic.
- **`ot` filters by crawl time, not publication time.** A feed that backfills old items will surface them in results even if they were published before the lookback window.
- **Zone 1 limit is 100 requests/day by default.** Monitor stderr output for usage. Inoreader can raise limits for publicly distributed apps but not for private developer apps.
- **Refresh tokens can be revoked.** If the human revokes access in Inoreader's connected-apps settings, the refresh token stops working. Fix: re-run `python3 auth.py` from scratch.
