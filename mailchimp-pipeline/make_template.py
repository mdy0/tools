#!/usr/bin/env python3
"""Generate template.html — a minimal, neutral Mailchimp classic-builder template.

Run: python3 make_template.py

This assembles the template from scratch in Python (string building) rather than transforming a
captured campaign — it's a generator script that produces a committed HTML file, in the same
relationship as any other build-output pair: edit this script, regenerate template.html, commit
both.

It demonstrates the two region shapes the legacy (classic) Mailchimp builder understands, and the
one trap that matters most:

- `mc:edit="banner"` sits directly on the `<img>` tag, with NO `mc:edit` on any ancestor. An
  Image content type requires the region on the `<img>` itself — a region one level up on the
  wrapping `<a>` or `<td>` silently suppresses the Image content type entirely, and once a
  campaign has been created from this template, nothing about that mistake is fixable by API
  (see API-NOTES.md). This generator refuses to write a template where that's true.
- Text regions are one styled `<div>` (or a heading element carrying the region itself) with no
  `<p>`, `<span>`, or styled `<a>` inside — any of those render as a blank editor pane in the
  legacy builder.

The self-checks below run before the file is written and exit non-zero on any failure — a broken
template should never reach disk.
"""

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUT_PATH = SCRIPT_DIR / 'template.html'

# Shared with newsletter_renderer.py's FONT_STACK so defaults and pushed content can't visually
# drift apart. Duplicated here (not imported) because make_template.py has no reason to depend on
# the push stack — but see newsletter_renderer.FONT_STACK for the source of truth.
FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

# The 12 regions this template must contain, in the order they appear. Heading regions carry
# their size via nested <span>s by design (the region sits on the heading element itself) --
# body regions must have none. The <p>/<span> self-check below only applies to DIV_REGIONS.
HEADING_REGIONS = ['intro_title', 'section_1_title', 'section_2_title', 'section_3_title', 'reflect_title']
DIV_REGIONS = ['intro_text', 'section_1_text', 'section_2_text', 'section_3_text', 'reflect_text', 'footer_text']
EXPECTED_REGIONS = ['banner'] + HEADING_REGIONS + DIV_REGIONS

PLACEHOLDER_BANNER_SRC = (
    'https://placehold.co/1200x200/1e293b/f1f5f9?text=BANNER+%E2%80%94+patched+by+push.py'
)


def _heading(region_name, default_text):
    return (
        f'<h2 style="text-align: left;" class="last-child" mc:edit="{region_name}">'
        f'<span style="font-size: 26px"><span style="font-family: {FONT_STACK}">'
        f'{default_text}</span></span></h2>'
    )


def _text_div(region_name, default_text):
    return (
        f'<div mc:edit="{region_name}" style="font-family: {FONT_STACK};font-size: 16px;'
        f'line-height: 1.5;mso-line-height-alt: 150%;text-align: left;">{default_text}</div>'
    )


def _section_block(n):
    return (
        f'<tr><td style="padding: 24px 24px 0 24px;" valign="top">\n'
        f'  {_heading(f"section_{n}_title", f"Section {n} headline")}\n'
        f'</td></tr>\n'
        f'<tr><td style="padding: 8px 24px 0 24px;" valign="top">\n'
        f'  {_text_div(f"section_{n}_text", f"Section {n} body text goes here.")}\n'
        f'</td></tr>'
    )


def build_html():
    sections = '\n'.join(_section_block(n) for n in (1, 2, 3))

    # No selector in this stylesheet names an anchor (e.g. "a", "a:hover", ".foo a") — that's the
    # legacy-builder discovery that anchor-naming CSS rules make hyperlinked text vanish from the
    # editing pane. check_no_anchor_selectors() below enforces it.
    style = """
    body { margin: 0; padding: 0; background: #f4f4f5; }
    table { border-collapse: collapse; }
    .container { max-width: 600px; margin: 0 auto; background: #ffffff; }
    """

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Newsletter</title>
<style type="text/css">{style}</style>
</head>
<body>
<center>
<table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0">
<tr><td style="padding: 0;">
  <a href="#">
    <img src="{PLACEHOLDER_BANNER_SRC}" alt="BANNER — patched by push.py" width="600"
         style="display:block;width:100%;max-width:600px;height:auto;" mc:edit="banner">
  </a>
</td></tr>
<tr><td style="padding: 24px 24px 0 24px;" valign="top">
  {_heading('intro_title', 'Intro heading goes here')}
</td></tr>
<tr><td style="padding: 8px 24px 0 24px;" valign="top">
  {_text_div('intro_text', 'Intro body text goes here.')}
</td></tr>
{sections}
<tr><td style="padding: 24px 24px 0 24px;">
  <hr style="border: 0;border-top: 2px solid #94a3b8;margin: 0;">
</td></tr>
<tr><td style="padding: 24px 24px 0 24px;" valign="top">
  {_heading('reflect_title', 'Worth Reflecting')}
</td></tr>
<tr><td style="padding: 8px 24px 24px 24px;" valign="top">
  {_text_div('reflect_text', 'Reflection questions go here.')}
</td></tr>
<tr><td style="padding: 16px 24px 24px 24px;" valign="top">
  <div mc:edit="footer_text" style="font-family: {FONT_STACK};font-size: 12px;line-height: 1.4;
       text-align: left;color: #71717a;">
    You're receiving this because you subscribed. *|UNSUB|*
  </div>
</td></tr>
</table>
</center>
</body>
</html>
"""


# ------------------------------------------------------------------ checks

VOID = {'img', 'br', 'hr', 'meta', 'input', 'link'}


def region_ancestors(html):
    """{region name on an <img>: [region names found on its ancestors]}."""
    stack, found = [], {}
    for m in re.finditer(r'<(/?)(\w+)\b([^>]*)>', html):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if closing:
            while stack and stack.pop()[0] != tag:
                pass
            continue
        region = re.search(r'mc:edit="([^"]+)"', attrs)
        if tag == 'img':
            if region:
                found[region.group(1)] = [r for _, r in stack if r]
            continue
        if tag not in VOID and not attrs.rstrip().endswith('/'):
            stack.append((tag, region.group(1) if region else None))
    return found


_ANCHOR_SELECTOR_RE = re.compile(r'(?:^|[},])\s*[^{}]*\ba\b[^{}]*\{', re.MULTILINE)


def check_no_anchor_selectors(style):
    if _ANCHOR_SELECTOR_RE.search(style):
        sys.exit('stylesheet contains a selector naming an anchor — this makes hyperlinked '
                  'text vanish from the legacy builder editing pane')


def check(html, style):
    names = re.findall(r'mc:edit="([^"]+)"', html)
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        sys.exit(f'duplicate region names: {dupes}')

    found = set(names)
    missing = sorted(set(EXPECTED_REGIONS) - found)
    extra = sorted(found - set(EXPECTED_REGIONS))
    if missing or extra:
        sys.exit(f'region set does not match EXPECTED_REGIONS — missing {missing}, extra {extra}')

    smothered = {img: anc for img, anc in region_ancestors(html).items() if anc}
    if smothered:
        sys.exit(f'image regions have an mc:edit ancestor, which suppresses the Image content '
                  f'type: {smothered}')

    for region_name in DIV_REGIONS:
        match = re.search(rf'mc:edit="{region_name}"[^>]*>(.*?)</div>', html, re.DOTALL)
        if not match:
            continue
        seg = match.group(1)
        for bad in ('<p', '<span'):
            if bad in seg:
                sys.exit(f'{region_name}: default content still contains {bad}> — the pane will render blank')
        for a in re.findall(r'<a\b[^>]*>', seg):
            if 'style' in a:
                sys.exit(f'{region_name}: default content has a styled link, pane will drop it — {a}')

    check_no_anchor_selectors(style)

    print(f'  {len(names)} regions, no duplicates, matches EXPECTED_REGIONS')
    print(f'  {len(region_ancestors(html))} image region(s), none smothered by an mc:edit ancestor')
    print('  text region defaults free of <p>/<span>, no styled links')
    print('  no anchor-naming selector in the stylesheet')


def main():
    html = build_html()
    style_match = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    style = style_match.group(1) if style_match else ''
    check(html, style)
    OUT_PATH.write_text(html, encoding='utf-8')
    print(f'wrote {OUT_PATH}')


if __name__ == '__main__':
    main()
