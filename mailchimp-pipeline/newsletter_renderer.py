"""Render ParsedNewsletter data into Mailchimp region HTML.

Pure functions only -- no network, no file writes. newsletter_markdown.py owns parsing; this
module turns its output into the exact markup shape the legacy (classic) builder produces
natively. A region whose content doesn't match that shape renders a blank editor pane, so nothing
here is cosmetic:

- No <p>. Paragraphs join with <br><br> inside one styled <div>.
- No <span> around a text run -- styling goes on the wrapper only.
- Links are bare <a href="..." target="_blank">label</a>; a styled <a> is dropped from the editor
  pane.
- `**bold**` markdown converts to <strong>, the one inline style tag that's safe here (unlike a
  styled <span> or <a>, <strong> carries no style attribute for the pane to choke on).

FONT_STACK is shared with make_template.py's default region text so the renderer's output and
the template's placeholders can't visually drift apart.
"""

import html
import re
from typing import Dict, List

from newsletter_markdown import ParsedNewsletter
from template_patcher import escape_attr

_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
_MD_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')

# Neutral system stack -- not a brand font. Shared with make_template.py.
FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

# Hanging-indent gutter for a bullet block, in pixels rather than a font-metric-dependent em
# value: a fixed-width floated column holds the bullet glyph, and the text column's margin-left
# matches it exactly, so every line of the item -- first and wrapped alike -- starts at precisely
# the same x position. A text-indent/padding-left pair (the first approach tried here) depends on
# the rendered width of "• " matching the chosen indent value, which is a font-metric guess and
# was visibly wrong twice (too wide at 1.6em, too narrow at 1em) before landing on this
# deterministic layout instead.
_BULLET_GUTTER_PX = 18


def escape_text(value: str) -> str:
    """Escape a value going into text content (not an attribute) -- the counterpart to
    template_patcher.escape_attr, used everywhere raw text (a heading, a section headline, the
    "via {source}" attribution) is written without going through format_text's markdown
    transforms. Escapes only &, <, > -- a text node has no attribute-quote boundary to protect,
    unlike escape_attr's `"`.

    Public: mailchimp_campaign.verify_rendered_html must compare a raw heading/headline/
    attribution string through this same transform, or it would false-fail against a campaign
    that was actually pushed correctly.
    """
    return html.escape(value, quote=False)


def bare_links(text: str) -> str:
    """Convert markdown [label](url) links to bare anchors, escaping every character of `text`
    exactly once along the way: walk the raw string match by match, escaping each non-link run as
    text (escape_text) and each link's label/href separately -- label as text content
    (escape_text), href as an HTML attribute value (escape_attr) -- as it's consumed. This is what
    lets the markdown link syntax be recognized against the *raw* text (escaping never touches
    `[`, `]`, `(`, `)`, so recognition doesn't actually depend on the ordering, but building the
    replacement from the raw captured groups, rather than re-escaping an already-substituted
    string, is what keeps every character escaped exactly once).
    """
    parts = []
    last = 0
    for m in _MD_LINK_RE.finditer(text):
        parts.append(escape_text(text[last:m.start()]))
        parts.append(f'<a href="{escape_attr(m.group(2))}" target="_blank">{escape_text(m.group(1))}</a>')
        last = m.end()
    parts.append(escape_text(text[last:]))
    return ''.join(parts)


def bold_text(text: str) -> str:
    """Convert markdown **bold** to <strong>. Runs after bare_links, so its input is already
    fully escaped (plain runs) and/or safe generated <a> markup (link runs) -- nothing here needs
    escaping again; wrapping the matched span in <strong> is purely structural. This also covers a
    bolded link (`**[label](url)**`): bare_links converts the link first, so the span this regex
    captures may itself contain an <a> tag, and it's wrapped as-is.
    """
    return _MD_BOLD_RE.sub(lambda m: f'<strong>{m.group(1)}</strong>', text)


def format_text(text: str) -> str:
    """Apply every inline markdown transform this tool supports, in one place, so every caller
    handles the same set consistently. Links first, then bold -- a bolded link
    (`**[label](url)**`) needs the link converted before the bold regex wraps the result.
    """
    return bold_text(bare_links(text))


def _is_bullet_block(paragraph: str) -> bool:
    """A "paragraph" (a blank-line-delimited chunk from split_paragraphs) is a bullet block when
    every one of its lines starts with "- " -- the same bullet marker FORMAT.md's Worth
    Reflecting list uses. Lines inside a bullet block have no blank line between them, so
    split_paragraphs never separates them; this is what tells them apart from ordinary prose that
    happens to span multiple lines.
    """
    lines = [line for line in paragraph.splitlines() if line.strip()]
    return bool(lines) and all(line.lstrip().startswith('- ') for line in lines)


# Vertical gap between one bullet item and the next, within the same block -- a little breathing
# room without the full paragraph-to-paragraph <br><br> gap.
_BULLET_ITEM_GAP = '6px'

# Marks a rendered chunk as "already block-level" (ends in a real block box with its own vertical
# rhythm) so _join_paragraphs can use a single <br> at that boundary instead of doubling up with
# the paragraph-to-paragraph <br><br> -- a bullet block's own <div>s already provide spacing.
_BLOCK_MARKER = '<div style="overflow: hidden;'


def render_paragraph(text: str) -> str:
    """Render one paragraph: a bullet block becomes one block-level <div> per item, each with a
    hanging indent (the floated bullet-glyph gutter described at _BULLET_GUTTER_PX) so a wrapped
    second line indents to align with the bullet's text instead of falling back to the left margin
    -- a plain "• " prefix joined with <br> looks fine for a one-line item but breaks the moment an
    item wraps. Anything else is ordinary prose with its markdown links and **bold** converted.
    Public: also used by
    mailchimp_campaign.verify_rendered_html to check text against the same transformation the
    renderer applies, since a paragraph's markdown -- and a bullet block's structure -- are both
    converted before they ever reach the rendered html.
    """
    if _is_bullet_block(text):
        items = [line.lstrip()[2:].strip() for line in text.splitlines() if line.strip()]
        return ''.join(
            f'<div style="overflow: hidden;margin-bottom: {_BULLET_ITEM_GAP};">'
            f'<div style="float: left;width: {_BULLET_GUTTER_PX}px;">•</div>'
            f'<div style="margin-left: {_BULLET_GUTTER_PX}px;">{format_text(item)}</div>'
            f'</div>'
            for item in items
        )
    return format_text(text)


def _styled_div(content: str, *, font_size: int, line_height, mso_line_height_alt: int) -> str:
    return (
        f'<div style="font-family: {FONT_STACK};font-size: {font_size}px;line-height: {line_height};'
        f'mso-line-height-alt: {mso_line_height_alt}%;text-align: left;">{content}</div>'
    )


def _join_paragraphs(paragraphs: List[str]) -> str:
    """Join rendered chunks with the normal <br><br> paragraph gap -- except right after a bullet
    block, which uses a single <br> instead: the block's own per-item margin-bottom already
    supplies spacing below it, so a full <br><br> there would double the gap. The gap *before* a
    bullet block stays a normal <br><br> -- a list still needs to visually separate from whatever
    precedes it, attribution line or prose alike.
    """
    parts = [paragraphs[0]] if paragraphs else []
    for prev, curr in zip(paragraphs, paragraphs[1:]):
        parts.append('<br>' if prev.startswith(_BLOCK_MARKER) else '<br><br>')
        parts.append(curr)
    return ''.join(parts)


def render_heading_spans(title: str) -> str:
    """intro_title / section_N_title / reflect_title -- every heading region in template.html
    (make_template.py's _heading()) carries mc:edit on the <h2> itself, so a sections write
    replaces the <h2>'s *inner* content only. The payload must therefore be spans, never a
    wrapping <h2> -- writing a full <h2>...</h2> here nests a second <h2> inside the template's,
    which rendered visually fine (browsers are forgiving of nested headings) but was wrong markup
    that no check caught, since verify_rendered_html only checks text presence, not structure.
    """
    return (
        '<span style="font-size: 26px">'
        f'<span style="font-family: {FONT_STACK}">{escape_text(title)}</span></span>'
    )


def render_intro_text(paragraphs: List[str]) -> str:
    # No leading-<br> visual tweak here -- that was a per-template judgment call on a specific
    # heading's own padding in the production template and doesn't generalize; every text
    # region here shares the same _join_paragraphs/_styled_div treatment.
    return _styled_div(
        _join_paragraphs([render_paragraph(p) for p in paragraphs]),
        font_size=16, line_height=1.5, mso_line_height_alt=150,
    )


def render_section_text(section) -> str:
    """section_N_text -- an attribution line and the summary paragraphs (with inline markdown
    links/bold converted), <br><br>-joined in one styled div. Links a section should carry go in
    the summary text as [label](url) inline links -- there is no other link slot.
    """
    paragraphs = [f'<em>via {escape_text(section.source)}</em>']
    paragraphs.extend(render_paragraph(p) for p in section.summary_paragraphs)
    return _styled_div(_join_paragraphs(paragraphs), font_size=16, line_height=1.5, mso_line_height_alt=150)


def render_reflect_text(questions: List[str]) -> str:
    return _styled_div(
        _join_paragraphs([render_paragraph(q) for q in questions]),
        font_size=16, line_height=1.5, mso_line_height_alt=150,
    )


def render_regions(parsed: ParsedNewsletter) -> Dict[str, str]:
    """All text regions push.py writes, keyed by region name. footer_text is
    deliberately absent -- it exists in template.html but push.py never
    writes it, which is the demonstration that an untargeted region doesn't
    move on a sections write.
    """
    regions = {
        'intro_title': render_heading_spans(parsed.intro_title),
        'intro_text': render_intro_text(parsed.intro_paragraphs),
        'reflect_title': render_heading_spans('Worth Reflecting'),
        'reflect_text': render_reflect_text(parsed.reflect_questions),
    }
    for i, section in enumerate(parsed.sections, start=1):
        regions[f'section_{i}_title'] = render_heading_spans(section.headline)
        regions[f'section_{i}_text'] = render_section_text(section)
    return regions
