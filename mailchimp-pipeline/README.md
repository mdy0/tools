# mailchimp-pipeline

## What it is

A two-stage newsletter pipeline that **deliberately stops at a draft**: it builds a reviewable draft Mailchimp campaign from a markdown file and never sends it. It uses Mailchimp's **classic (legacy) coded-template API path** — not the newer drag-and-drop builder, which behaves differently under the API and isn't what this tool targets (see API-NOTES.md).

- **Stage 1 (`collect.py`)** reads a Google Sheet where newsletter content has been gathered and writes one markdown file: the complete, reviewable, re-runnable source of truth for the send.
- **Stage 2 (`push.py`)** reads that markdown file and builds a draft campaign in Mailchimp — uploads the banner image, patches a template, creates the campaign, writes every content section, and verifies what was actually stored. **It never sends, tests, resumes, or schedules a campaign** — that's a hard rule enforced in the client, not just a convention (see AGENTS.md).

```text
+--------------+
| Google Sheet |  (or any source you adapt Stage 1 to)
+------+-------+
       |
       |  collect.py -- Stage 1: reads cells per
       |  config.json, writes one markdown file
       v
+-------------------------------+
| newsletter-YYYY-MM-DD.md      |  the contract (FORMAT.md)
| + images/banner.png (you      |  reviewable source of truth
|   supply the banner file)     |
+------+----------------+-------+
       |                |
       |                |  preview.py (optional fast loop,
       |                |  no network, no account)
       |                v
       |         preview.html
       |                |
       v                v
+-------------------------------------------------+
| Human reviews: reads the markdown, and looks at |
| the preview in a browser if one was rendered    |
+------+------------------------------------------+
       |
       v
push.py -- Stage 2: fixed order, never sends
       |
       |  0. (--live-template only) health-check that template
       |  1. upload banner ----------> Mailchimp File Manager
       |  2. patch banner URL into a COPY of template.html
       |  3. push the patched copy:
       |       default -------------> POST new throwaway template
       |       --live-template <id> -> PATCH that existing template
       |  4. POST campaign ----------> DRAFT (from that template)
       |  5. PUT text sections into the draft (sections only)
       |  6. GET rendered html back, verify every piece landed
       v
Draft campaign in Mailchimp
       |
       v
Human reviews & schedules in the Mailchimp UI
(the tool has no send/schedule path -- hard-blocked in the client)
```

The markdown file in between is the contract: a human reads it before anything touches the network, the push stage is mechanical — plain deterministic scripts, no AI anywhere in the loop when you run them — and a failed or partial push can be re-run from the same file. AI comes in only when building or adapting the tool itself: point a coding agent at this repo and have it rewrite Stage 1 for your own data source; Stage 2 and the safety invariants carry over unchanged. See "For AI coding agents" below.

The repo ships a ready-to-push sample newsletter (`sample/newsletter-2026-08-02.md`) together with its banner image (`sample/images/banner.png`), so Stage 2 works out of the box with nothing but a Mailchimp account: clone, fill in `.env` (API key plus a from-name and reply-to address, both required by Mailchimp), run `push.py`, and a real draft appears in your account.

## Safety model

The safety rules are enforced in code, not just documented:

- **No send path exists.** Send, test-send, resume, and schedule are hard-blocked in the API client before any HTTP call happens — the human schedules the reviewed draft in the Mailchimp UI.
- **Content writes are surgical.** Campaign content is only ever written as named template sections, never as a whole-body `html` payload (which Mailchimp accepts with a 200 and silently wipes).
- **Every write is verified.** A successful API response is not trusted; the rendered campaign is re-fetched and checked against what was pushed, every run.
- **Deletes are gated.** The tool only deletes campaigns it marked as its own throwaways, and never a scheduled one.

[AGENTS.md](AGENTS.md) is the authoritative safety contract; [API-NOTES.md](API-NOTES.md) documents the observed Mailchimp behavior behind each rule. For the `mc:edit`/`mc:hideable` markup that makes a region editable or hideable in the Mailchimp Web Admin UI in the first place, [docs/editable-regions.md](docs/editable-regions.md) is the how-to.

## One-time human setup

1. **Create a Mailchimp account**, if you don't already have one: [mailchimp.com/signup](https://mailchimp.com/signup/), free plan is fine (this tool only ever creates drafts, so you won't hit send limits). Any business-name/onboarding answers work — they aren't user-facing for a throwaway test.
2. **Create an audience (list)**, if one wasn't created for you during onboarding: **Audience → Create Audience**, filling in the required contact/permission-reminder fields with placeholder info. This tool never emails anyone, so the audience just needs to exist.
3. **Get an API key**: profile icon (bottom left) → **Profile** → **Extras** → **API keys** → **Create A Key**. Copy the whole thing — the data-center suffix at the end (e.g. `-us1`, `-us21`) is part of the key itself, not a separate setting.
4. **`cp .env.example .env`** and fill in `MAILCHIMP_API_KEY`, `MAILCHIMP_FROM_NAME`, `MAILCHIMP_REPLY_TO` (Mailchimp rejects a campaign missing either of the last two — any values work for a test run).
5. **`MAILCHIMP_AUDIENCE_ID` is optional.** If your account has exactly one audience, leave it unset — `push.py` looks it up automatically (`GET /lists`) and tells you which one it used. If you have more than one, `push.py` prints every audience id/name on its first run and asks you to set this variable.
6. **Only if you want to run Stage 1** against a Google Sheet: a free Google Sheets API key (Google Cloud console → enable the Sheets API → Credentials → API key) as `GOOGLE_SHEETS_API_KEY` in `.env`. Stage 2 needs nothing Google. This API-key path only works for a sheet shared "Anyone with the link — Viewer" (like the demo sheet); a **private** sheet needs OAuth instead — not shipped here, but the swap is contained: replace `collect.py`'s `read_range` with a call using an OAuth-authenticated `google-api-python-client` `Sheets` service instead of a plain `requests.get`, and drop the `GOOGLE_SHEETS_API_KEY` env var for a stored OAuth token. Everything below `read_range` (`fetch_newsletter`, `write_markdown`) is unaffected.

## Deployment options

- **Run in place from a clone (default).** Clone this repo, `cd mailchimp-pipeline`, follow Usage below. Simplest option; fine for a one-off send or evaluating the pattern.
- **Copy the directory into your own project.** Everything this tool needs is inside `mailchimp-pipeline/` — no dependency on the rest of this repo. Copy the directory, keep your own `.env`, and adapt `collect.py` to your data source (see "For AI coding agents"). Use this when the pipeline becomes a real part of your project's workflow rather than a one-off.

## Usage

Four workflows, ordered from least setup to the full pipeline, then a flag reference. Each workflow builds on the one before it.

### Workflow 1 — Preview the sample locally (no Mailchimp account, nothing remote)

1. **Render the sample**: `python3 preview.py` — writes `preview.html` in this directory and opens it in your browser.
   `preview.py` uses only the Python standard library, so this works even before `pip install -r requirements.txt` (the later workflows do need the install).

`preview.py` uses the exact same rendering code `push.py` does, so it's the fast loop for checking region content, bullet/bold formatting, and layout before spending a `push.py` run on it. It's not a byte-exact match for Mailchimp's own editor pane, though — that pane has diverged from plain browser CSS before (see API-NOTES.md) — so confirm anything that matters with a real throwaway push.

### Workflow 2 — Clone-to-draft: push the committed sample to a real draft

1. **`cd mailchimp-pipeline`**
2. **`cp .env.example .env`** and fill in your Mailchimp key, from-name, and reply-to (One-time human setup above).
3. **`pip install -r requirements.txt`**, if you haven't already.
4. **`python3 push.py`** — pushes `sample/newsletter-2026-08-02.md` by default.

`push.py` prints the campaign id, web id, template id, and banner URL as it goes, and opens the draft's editor URL in your browser (`--no-open` to suppress that).

This is the full pushed draft as Mailchimp renders it, from the committed sample — banner, intro, all three sections (attribution lines, bullet lists, bold, inline links), the divider, Worth Reflecting, and the footer placeholder the push deliberately never touches:

![The complete sample newsletter as a draft campaign rendered by Mailchimp](docs/draft-in-mailchimp.png) "Opens in your browser" means macOS's `open` command specifically, for both `push.py` and `preview.py` — on any other OS (or if `open` isn't found) `push.py` just prints the URL for you to open by hand, while `preview.py` falls back to Python's `webbrowser` module instead. Neither behavior is configurable; if `webbrowser`'s guess at a browser is wrong on your system, open the printed/written path yourself.

### Workflow 3 — Push your own newsletter

1. **Write a markdown file** matching [FORMAT.md](FORMAT.md) — easiest is copying the sample and editing it.
2. **Place your banner image** at the path the `**Banner:**` field names, relative to the markdown file itself (e.g. `images/banner.png` in an `images/` directory beside it). Nothing in this pipeline creates or fetches that file for you — see Workflow 4, step 3 for the full story.
3. **Preview it**: `python3 preview.py path/to/your.md`
4. **Dry-run it**: `python3 push.py --dry-run path/to/your.md` — catches a malformed file with zero network calls.
5. **Push it**: `python3 push.py path/to/your.md`

### Workflow 4 — Full pipeline from a Google Sheet

Works out of the box against the shared demo sheet at [docs.google.com/spreadsheets/d/1brC4EiAATWxQDRIL6zLQuR5chmwCWum459-rh1-Jxgw](https://docs.google.com/spreadsheets/d/1brC4EiAATWxQDRIL6zLQuR5chmwCWum459-rh1-Jxgw/edit) — `config.json` already points at it, and `sheet-layout.md` documents its tab/cell layout.

1. **Get a `GOOGLE_SHEETS_API_KEY` into `.env`** (One-time human setup, step 6). Only this workflow needs it — Stage 2 needs nothing Google.
2. **`cd mailchimp-pipeline && python3 collect.py`** — writes `newsletter-YYYY-MM-DD.md` beside the script, named from the sheet's own Date field (`--out` to choose a different path). Stay in this directory for step 5 — the filename there is resolved from wherever you run the command.
3. **Place the banner image beside the markdown.** `collect.py` never produces the banner image, only the reference to it: the sheet's "Banner filename" cell (`Meta!B4`, e.g. `banner.png`) becomes `**Banner:** images/banner.png` in the written markdown — a path `push.py` resolves relative to the markdown file's own directory. Put the actual image at `images/<that filename>` beside the markdown yourself (with step 2's default output path, that means an `images/` directory here in `mailchimp-pipeline/`; the shipped `sample/images/banner.png` is a separate copy used only by the committed sample, and doesn't cover this path).
4. **Review the markdown** — that review is the whole point of the two-stage design.
5. **Push it**: `python3 push.py newsletter-YYYY-MM-DD.md` (the actual date-stamped filename step 2 printed).

**Plugging in your own Google Sheet** (same tabs/cells, different content): no code change needed. Copy the demo sheet's tab layout (`Meta`, `Theme 1`, `Theme 2`, `Theme 3`, `Reflect` — see `sheet-layout.md` for the exact cell map), fill in your own content, share it at least "Anyone with the link — Viewer" (or use the OAuth upgrade path for a private sheet — see One-time human setup step 6 above), and point `config.json`'s `spreadsheet_id` at your sheet's id instead. `collect.py` doesn't care whose sheet it is, only that the cells match.

### Flag reference

```bash
python3 push.py --dry-run              # render everything locally, touch nothing remote
python3 push.py --no-images            # skip the banner upload (see the per-mode note below the flag reference)
python3 push.py --no-open              # don't open the draft's editor URL in the browser
python3 push.py --live-template 123456 # PATCH an existing template instead of a throwaway copy
python3 push.py --throwaway-template-name my-check  # name the throwaway template (default: newsletter-check-{date})
python3 push.py --delete-throwaway <campaign_id>  # delete a throwaway draft (title must carry 🔍, status must not be "schedule")
```

**`--live-template` overwrites, it doesn't merge — except with `--no-images`.** `push.py` normally PATCHes the *entire* local `template.html` over whatever template id you give `--live-template` — that's correct for a template this pipeline owns (re-running keeps it in sync with the generator), but it will clobber the stored design of any other template you point it at, including a hand-built one. Only pass plain `--live-template` at a template you're comfortable being fully overwritten by this tool's own `template.html`. Also note that with `--live-template`, a health check on that template — a network GET — runs before anything else in the run, so a deleted or drag-and-drop template aborts the push before any upload (see API-NOTES.md).

**`--no-images` means something different depending on which template mode it's paired with:**
- **Throwaway (default, no `--live-template`)**: skips the banner upload; the new template still ships with the generator's placeholder banner, since there's no live template to leave alone.
- **`--live-template` + `--no-images` together**: skips the template PATCH *entirely* — no upload, no patch, no write to the live template's stored html at all. The campaign is created straight from the live template's current content, and only the text sections get written. This is the only way to refresh a live template's text without touching its banner.

## Integration

**From a shell pipeline or Makefile:**

```bash
python3 collect.py --out newsletter.md && python3 push.py newsletter.md
```

`push.py` always exits non-zero on failure — the exit code alone doesn't distinguish "nothing was created" from "a draft exists but needs a look," so don't script against it. Check the output instead: a printed `Campaign created: campaign_id=...` line (which appears as soon as the campaign exists, before sections are written or verified) means a draft is sitting in Mailchimp regardless of what happens afterward; its absence means the run aborted before anything was created.

**Pointing Stage 1 at another source:** `read_range` (and the small wrapper `_read_cell`) is the one function that actually talks to Google. `write_markdown` is genuinely source-agnostic — it only assembles markdown from a plain dict, unchanged for any source. `fetch_newsletter` sits in between: it walks `config.json`'s `tab`/cell shape and calls `_read_cell`, so it keeps working unchanged only if your replacement source is still naturally addressed as "tab + cell" (e.g. a different spreadsheet API) — for a source that isn't cell-shaped (a CMS, a different config shape), rewrite `fetch_newsletter`'s body too, producing the same dict shape `write_markdown` expects.

## For AI coding agents

**Prerequisites the human must do first** (you can't do these — they need an account and a browser): a Mailchimp API key in `.env` (see One-time human setup above); if adapting Stage 1 to a non-Google source, whatever credential that source needs.

**Adaptation runbook** — Stage 1 is the part you rewrite; Stage 2 and the safety invariants are not:

1. **Read `AGENTS.md` before touching anything.** It states the non-negotiable safety rules — never weaken them while adapting the rest.
2. **Read `FORMAT.md`.** It's the full markdown contract, precise enough to write a new collector against without reading `collect.py`. Whatever you swap Stage 1 for, its job is to produce a file matching that shape exactly.
3. **Edit `collect.py`'s adaptation seam (see the module docstring for the exact boundary), and check `fetch_newsletter`.** The seam is `read_range`, `_read_cell`, and `_google_api_key` — the only code that talks to Google or reads `GOOGLE_SHEETS_API_KEY`; replace all three with reads from, and credential handling for, your own source (`main()` calls `_google_api_key()` rather than reading the env var itself, so this brings its own credential handling with it — no Google residue left in `main()`). `fetch_newsletter` walks `config.json`'s tab/cell shape on top of that; it survives unchanged only if your new source is still naturally "tab + cell" addressed. For a source shaped differently, rewrite `fetch_newsletter`'s body too — `write_markdown` is the part that's truly source-agnostic (it only assembles markdown from a plain dict) and never needs to change.
4. **Keep the section count in sync with the template.** The contract is exactly three `## This Week` section blocks because `make_template.py` hardcodes three section slots when it generates `template.html` — enforced by `newsletter_markdown.py`'s parser, which aborts and names the count it found if a markdown file has a different number. `newsletter_renderer.py` is count-agnostic (it just loops over however many sections it's handed) and never needs to change for this. Changing the count means editing `make_template.py` and regenerating `template.html` from it (never hand-edit `template.html` — it's generated output), plus updating that count check in `newsletter_markdown.py` — it is not a Stage-1-only change (see step 5: don't make this change while only adapting Stage 1).
5. **Leave `push.py`, the `mailchimp_*.py` modules, `template_patcher.py`, `make_template.py`, and `newsletter_markdown.py`/`newsletter_renderer.py` unchanged**, along with every rule in `AGENTS.md`, *unless* you're deliberately changing the section count per step 4 above — that's the one sanctioned edit, and it touches `make_template.py` and `newsletter_markdown.py`, never `newsletter_renderer.py`. Everything else in this list is already correct and already safety-checked; the whole point of the markdown contract is that Stage 2 never needs to know where Stage 1's data came from.
6. **Verify with `--dry-run` first**, then a real throwaway push, before trusting the adaptation: `python3 push.py --dry-run path/to/your.md` catches a malformed markdown file with zero network calls.

**What to watch out for:**

- **Silent 200s.** `PUT /campaigns/{id}/content` with an `html` key returns 200 and wipes the campaign body. A sections write containing `mc:edit` anywhere in its value is silently discarded. Neither raises an error — see API-NOTES.md.
- **The image write-order trap.** Image regions are invisible to the API once a campaign exists. If you're extending this tool to patch more images, they must go into the template **before** `create_campaign` runs, never after.
- **`stem.NN` upload duplicates.** Mailchimp's File Manager has no overwrite — a re-upload under an existing name lands as `name.01.ext`, `name.02.ext`, etc. `mailchimp_assets.upload_asset` already handles this (search the whole family for a size match before uploading fresh); don't bypass it with a raw `MailchimpClient.upload_file` call — that's the single-call upload `upload_asset` wraps, deliberately named differently so the two are never confused.
- **`web_id` ≠ `campaign_id`.** The editor URL uses `web_id`; every other API call needs `campaign_id`. They're printed together in the final report for exactly this reason.
- **This tool targets the classic/legacy template API path.** The newer drag-and-drop builder behaves differently under the API in ways the official Mailchimp docs don't distinguish. If you're adapting this for an account whose templates are drag-and-drop, most of Stage 2 doesn't apply as-is — read API-NOTES.md's "classic vs. new builder" section first.
