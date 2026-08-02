#!/usr/bin/env python3
"""Render a newsletter markdown file into a local HTML file, using template.html and the same
region-rendering code push.py uses -- no network, no Mailchimp account needed.

This is not a byte-exact preview of the Mailchimp editor pane (Mailchimp re-indents and inlines
CSS on render, and its own wrapper markup differs from a bare browser view) -- it's the fast local
loop for checking region content and layout (bullet indents, bold, link styling) before spending a
push.py run on it. That reformatting is whitespace/wrapper-level, not content-level: it hasn't
broken mailchimp_campaign.verify_rendered_html's exact-substring matching of pushed text across any
live push this project has done, so region content that looks right here has been a reliable
signal for what lands in Mailchimp. Push a throwaway draft and look at the real editor/preview pane
to confirm anything that matters for the legacy-builder-specific quirks in API-NOTES.md.
"""

import argparse
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

from mailchimp_assets import AssetError, resolve_asset_path
from newsletter_markdown import NewsletterMarkdownError, parse_newsletter_markdown
from newsletter_renderer import render_regions
from template_patcher import patch_banner

SCRIPT_DIR = Path(__file__).parent
DEFAULT_MARKDOWN_PATH = SCRIPT_DIR / 'sample' / 'newsletter-2026-08-02.md'
TEMPLATE_PATH = SCRIPT_DIR / 'template.html'


def _find_element_span(html: str, region_name: str):
    """Locate the (inner_start, inner_end) byte offsets of the element carrying
    mc:edit="{region_name}", by counting nested same-tag opens/closes -- a naive non-greedy
    regex would stop at the first nested closing tag, which breaks the moment a region's content
    contains its own nested <div>s (a bullet block does).
    """
    match = re.search(rf'<(\w+)([^>]*\bmc:edit="{re.escape(region_name)}"[^>]*)>', html)
    if not match:
        raise ValueError(f'region not found in template: {region_name}')
    tag = match.group(1)
    inner_start = match.end()
    depth = 1
    tag_re = re.compile(rf'<(/?){tag}\b[^>]*?(/?)>')
    for tag_match in tag_re.finditer(html, inner_start):
        if tag_match.group(1) == '/':
            depth -= 1
            if depth == 0:
                return inner_start, tag_match.start()
        elif not tag_match.group(2):
            depth += 1
    raise ValueError(f'unbalanced tag for region: {region_name}')


def render_preview_html(markdown_path: Path) -> str:
    parsed = parse_newsletter_markdown(markdown_path)
    html = TEMPLATE_PATH.read_text(encoding='utf-8')

    # Routed through the same resolve_asset_path the real run uses (not a separate inline
    # resolve()) so a containment-violating **Banner:** path is refused here too, not just in
    # push.py -- a preview that happily read outside markdown_dir would defeat the point of the
    # contract existing at all. Preview only ever leaves the placeholder banner on any problem
    # (missing or refused), never uploads anything, so a refused path fails soft here, not hard --
    # but it's reported distinctly from a merely-missing one.
    try:
        banner_path = resolve_asset_path(markdown_path.parent, parsed.banner_path)
    except AssetError as e:
        print(f'Banner refused ({e}) -- leaving the template placeholder banner.')
        banner_path = None

    if banner_path is not None and banner_path.exists():
        html = patch_banner(html, banner_path.as_uri(), parsed.banner_alt, parsed.banner_link)
    elif banner_path is not None:
        print(f'Banner file not found ({banner_path}) -- leaving the template placeholder banner.')

    for name, content in render_regions(parsed).items():
        inner_start, inner_end = _find_element_span(html, name)
        html = html[:inner_start] + content + html[inner_end:]
    return html


def main():
    parser = argparse.ArgumentParser(description='Render a newsletter markdown file to a local HTML preview')
    parser.add_argument('markdown_path', nargs='?', default=str(DEFAULT_MARKDOWN_PATH),
                        help=f'Path to the newsletter markdown file (default: {DEFAULT_MARKDOWN_PATH})')
    parser.add_argument('--out', help=f'Output HTML path (default: {SCRIPT_DIR / "preview.html"})')
    parser.add_argument('--no-open', action='store_true', help='Do not open the result in a browser')
    args = parser.parse_args()

    md_path = Path(args.markdown_path)
    try:
        html = render_preview_html(md_path)
    except NewsletterMarkdownError as e:
        sys.exit(f'Error parsing {md_path}: {e}')

    # Never sample/ -- the committed sample stays frozen at run time, same rule as collect.py's
    # default output path. Enforced, not just a default: an explicit --out inside sample/ is
    # refused too.
    out_path = Path(args.out) if args.out else SCRIPT_DIR / 'preview.html'
    if (SCRIPT_DIR / 'sample').resolve() in out_path.resolve().parents:
        sys.exit(f'Refusing to write into {SCRIPT_DIR / "sample"} -- the committed sample stays '
                  f'frozen. Pass a different --out path.')
    out_path.write_text(html, encoding='utf-8')
    print(f'Wrote {out_path}')

    if not args.no_open:
        try:
            subprocess.run(['open', str(out_path)], check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            webbrowser.open(out_path.as_uri())


if __name__ == '__main__':
    main()
