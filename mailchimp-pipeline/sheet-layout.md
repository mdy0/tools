# sheet-layout.md — the demo Google Sheet

`collect.py` (Stage 1) reads a Google Sheet and writes a file in the [FORMAT.md](FORMAT.md) shape. This file documents the sheet's tab/cell layout, maps it to `config.json`, and — for the shared demo sheet specifically — records how it was set up, as a reference for setting up your own.

**The shared demo sheet already exists and is live**: [AI This Week — demo (mailchimp-pipeline)](https://docs.google.com/spreadsheets/d/1brC4EiAATWxQDRIL6zLQuR5chmwCWum459-rh1-Jxgw/edit?gid=0#gid=0), shared "Anyone with the link — Viewer." `config.json`'s `spreadsheet_id` already points at it, so `python3 collect.py` works against it out of the box (once you have your own `GOOGLE_SHEETS_API_KEY` — see below). Open the sheet alongside the table below to see the cell layout described here match the real thing — its content is always kept byte-identical to `sample/newsletter-2026-08-02.md`, so that file is the reference for what the sheet actually contains.

Deliberately simple: single values at single cells, no merged ranges, no rich-text reading, no checkboxes. The point is the pattern (fields live at named cells, `config.json` maps them), because anyone adapting this tool will remap it to their own sheet anyway.

## Tab/cell layout

| Tab | Cell | Field |
|---|---|---|
| Meta | B1 | Date (`2026-08-02`) |
| Meta | B2 | Subject |
| Meta | B3 | Preview Text |
| Meta | B4 | Banner filename (`banner.png`) |
| Meta | B5 | Banner alt |
| Meta | B6 | Banner link (leave blank for "not linked" — equivalent to `—` in the markdown) |
| Meta | B7 | Intro heading |
| Meta | B8 | Intro paragraphs (multi-line cell, blank line between paragraphs) |
| Theme 1 | B1 | Headline |
| Theme 1 | B2 | Source (attribution) |
| Theme 1 | B3 | Summary (multi-line cell; inline links written as `[label](url)` markdown, `**bold**` for emphasis, and a run of `- ` lines renders as a bullet list — see FORMAT.md. No rich-text/`textFormatRuns` reading needed, which is the deliberate simplification here) |
| Theme 2 | B1–B3 | same shape as Theme 1 |
| Theme 3 | B1–B3 | same shape as Theme 1 |
| Reflect | B1:B5 | one question per row; blank rows are ignored |

Column A of every tab holds a human-readable label (`Subject`, `Headline`, …) so the sheet is self-describing to a person looking at it. `collect.py` only ever reads column B (and `Reflect!B1:B5`) — column A is documentation, not data.

## `config.json`

`config.json` in this directory maps every field above to `Tab!Cell`. It is not a secret (the sheet URL itself is public in the README), so the spreadsheet id lives here, not in `.env`.

## Google Sheets API key

Needed by every user who wants to run `collect.py` (against the demo sheet or your own) — not a one-time setup step tied to the demo sheet itself. Google Cloud console → any project → enable the **Google Sheets API** → Credentials → Create API key. Put it in your local `.env` as `GOOGLE_SHEETS_API_KEY`. It does not need to go anywhere public, and `push.py` needs nothing Google — only `collect.py` reads it.

## Setting up your own sheet

Copy the Tab/cell layout above into a fresh sheet, then two gotchas worth knowing before you paste content in:

- **Multi-line cells** (`Meta!B8`, every `Theme N!B3`) need **Ctrl/Cmd+Enter** between lines, not a plain Enter — a plain Enter jumps to the next cell instead of adding a line break inside the current one, which silently flattens the paragraph structure.
- **Sharing**: at least "Anyone with the link — Viewer" for the plain-API-key read path this tool uses by default. A private sheet needs the OAuth upgrade path instead — see README's One-time human setup.

Then point `config.json`'s `spreadsheet_id` at your sheet's id.

## Keeping the sheet and sample in sync

Whenever either changes, run `python3 collect.py --out /tmp/check.md && diff /tmp/check.md sample/newsletter-2026-08-02.md`. It should be empty; if it isn't, one of the two needs to be reconciled with the other (whichever is authoritative for that change).
