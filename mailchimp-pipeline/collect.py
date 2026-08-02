#!/usr/bin/env python3
"""Stage 1: read a Google Sheet (see sheet-layout.md) and write a newsletter markdown file
conforming to FORMAT.md.

Read-everything-then-write-one-file: nothing here talks to Mailchimp, and this script never
overwrites sample/ -- the committed sample stays frozen so it can be byte-compared against fresh
output. push.py (Stage 2) needs nothing this script produces here at import time; it only reads
whatever markdown file it's pointed at.

Adaptation seam (the single source of truth for this file's layout -- both seam-marker comments
below are pure delimiters, deliberately without their own copy of this explanation, so there's
nothing left to drift out of sync with it): read_range(), _read_cell(), and _google_api_key() are
the only Google-specific code in this file -- replace all three with reads from, and credential
handling for, your own data source. main() calls _google_api_key() rather than reading
GOOGLE_SHEETS_API_KEY itself, so replacing the seam naturally replaces main()'s credential
requirement too; a source with no credential (or a differently named one) means rewriting or
dropping that one function, never touching main(). fetch_newsletter() sits just after the seam and
still calls _read_cell(), so it survives unchanged only if your source is still naturally addressed
as "tab + cell"; a differently-shaped source (a CMS, a REST API) needs fetch_newsletter's body
rewritten too. write_markdown() is the one function that's genuinely source-agnostic -- it only
assembles markdown from a plain dict, and needs no changes for any source, as long as you hand it
the same shape of dict.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / 'config.json'

_SPREADSHEET_ID_IN_URL_RE = re.compile(r'/spreadsheets/d/([a-zA-Z0-9-_]+)')


def extract_spreadsheet_id(value: str) -> str:
    """Accept either a bare spreadsheet id or a full Google Sheets URL --
    config.json may hold whichever is more convenient to paste.
    """
    match = _SPREADSHEET_ID_IN_URL_RE.search(value)
    return match.group(1) if match else value


# ---------------------------------------------------------------------------
# Adaptation seam starts here -- see the module docstring for what to replace.
# ---------------------------------------------------------------------------

def read_range(spreadsheet_id: str, range_notation: str, api_key: str) -> list:
    """GET the Sheets values endpoint for one range. Works for any sheet
    shared "Anyone with the link — Viewer" -- no OAuth, no service account.
    A private sheet needs the OAuth upgrade path described in README.md.

    Returns the raw `values` list of rows (each a list of cell strings);
    Google omits trailing empty cells/rows entirely, so callers must not
    assume a fixed shape.
    """
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_notation}'
    r = requests.get(url, params={'key': api_key}, timeout=30)
    if r.status_code >= 400:
        # Never let the key reach an error message or traceback -- requests' own
        # raise_for_status() includes the full request URL, query string and all, which would
        # print GOOGLE_SHEETS_API_KEY in plain text.
        try:
            detail = r.json()
        except ValueError:
            detail = r.text
        raise RuntimeError(f'Sheets API error reading {range_notation!r}: HTTP {r.status_code}: {detail}')
    return r.json().get('values', [])


def _read_cell(spreadsheet_id: str, tab: str, cell: str, api_key: str) -> str:
    values = read_range(spreadsheet_id, f"'{tab}'!{cell}", api_key)
    if not values or not values[0]:
        return ''
    return values[0][0]


def _google_api_key() -> str:
    api_key = os.getenv('GOOGLE_SHEETS_API_KEY')
    if not api_key:
        sys.exit('GOOGLE_SHEETS_API_KEY not set in .env (push.py does not need this -- '
                  'it only reads the markdown file this script writes).')
    return api_key

# ---------------------------------------------------------------------------
# End of the adaptation seam.
# ---------------------------------------------------------------------------


def fetch_newsletter(config: dict, api_key: str) -> dict:
    """Walk config.json and return a plain dict shaped for write_markdown.
    One read_range call per tab (not per cell) would be faster, but this
    stays a small, obvious 1:1 mapping to config.json's field list.
    """
    spreadsheet_id = extract_spreadsheet_id(config['spreadsheet_id'])
    meta_cfg = config['meta']
    meta_tab = meta_cfg['tab']

    meta = {
        field: _read_cell(spreadsheet_id, meta_tab, cell, api_key)
        for field, cell in meta_cfg.items() if field != 'tab'
    }

    sections = []
    for section_cfg in config['sections']:
        tab = section_cfg['tab']
        sections.append({
            field: _read_cell(spreadsheet_id, tab, cell, api_key)
            for field, cell in section_cfg.items() if field != 'tab'
        })

    reflect_cfg = config['reflect']
    reflect_rows = read_range(spreadsheet_id, f"'{reflect_cfg['tab']}'!{reflect_cfg['range']}", api_key)
    reflect_questions = [row[0].strip() for row in reflect_rows if row and row[0].strip()]

    return {'meta': meta, 'sections': sections, 'reflect_questions': reflect_questions}


def write_markdown(data: dict, out_path: Path) -> None:
    """Assemble exactly the FORMAT.md shape. Multi-line cells pass through
    with their internal blank lines intact -- the Sheets values endpoint
    returns '\\n' in-cell verbatim for a cell whose line breaks were entered
    with Ctrl/Cmd+Enter.
    """
    meta = data['meta']
    banner_link = meta.get('banner_link', '').strip() or '—'

    lines = [
        '# Newsletter',
        '',
        f"**Subject:** {meta['subject']}",
        f"**Preview Text:** {meta['preview_text']}",
        f"**Date:** {meta['date']}",
        f"**Banner:** images/{meta['banner_file']}",
        f"**Banner Alt:** {meta['banner_alt']}",
        f"**Banner Link:** {banner_link}",
        '',
        '## Intro',
        '',
        f"### {meta['intro_title']}",
        '',
        meta['intro_text'].strip(),
        '',
        '## This Week',
        '',
    ]

    for i, section in enumerate(data['sections']):
        lines.extend([
            f"### {section['headline']}",
            '',
            f"**Source:** {section['source']}",
            '',
            section['summary'].strip(),
            '',
        ])
        if i < len(data['sections']) - 1:
            lines.extend(['---', ''])

    lines.append('## Worth Reflecting')
    lines.append('')
    for question in data['reflect_questions']:
        lines.append(f'- {question}')

    out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Stage 1: read a Google Sheet, write a newsletter markdown file')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH), help='Path to config.json')
    parser.add_argument('--out', help='Output path (default: newsletter-YYYY-MM-DD.md beside this script, '
                                       'using the sheet\'s own Date field)')
    args = parser.parse_args()

    load_dotenv(SCRIPT_DIR / '.env')
    api_key = _google_api_key()

    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    data = fetch_newsletter(config, api_key)

    out_path = Path(args.out) if args.out else SCRIPT_DIR / f"newsletter-{data['meta']['date']}.md"
    if (SCRIPT_DIR / 'sample').resolve() in out_path.resolve().parents:
        sys.exit(f'Refusing to write into {SCRIPT_DIR / "sample"} -- the committed sample stays '
                  f'frozen. Pass a different --out path.')
    write_markdown(data, out_path)
    print(f'Wrote {out_path}')
    print('Review the markdown before running push.py against it -- that review is the whole point.')


if __name__ == '__main__':
    main()
