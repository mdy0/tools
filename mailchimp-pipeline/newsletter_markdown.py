"""Parse a newsletter markdown file (see FORMAT.md) into a structured object.

push.py reads this file rather than any upstream data source directly, so a human's review of
the markdown -- and any hand-edits to it -- are what actually get pushed.
"""

import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class NewsletterMarkdownError(ValueError):
    """Raised for anything that should abort the run: a missing required
    field, a section count that doesn't match the template, or a malformed
    block. Abort before anything touches the network, don't guess.
    """


@dataclass
class Section:
    headline: str
    source: str
    summary_paragraphs: List[str]


@dataclass
class ParsedNewsletter:
    subject: str
    preview_text: str
    date: str
    banner_path: str
    banner_alt: str
    banner_link: Optional[str]
    intro_title: str
    intro_paragraphs: List[str]
    sections: List[Section]
    related_reading_links: List[str]
    reflect_questions: List[str]


def _required_field(pattern, text, name):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise NewsletterMarkdownError(f"Could not find **{name}:** in markdown")
    return match.group(1).strip()


def split_paragraphs(text):
    """Split on blank lines. Shared with newsletter_renderer.py -- section
    summaries and the intro come back from the parser as one string with
    their blank lines intact, and the renderer needs the same splitting rule.
    """
    return [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]


def _parse_date(text):
    """**Date:** must be YYYY-MM-DD -- checked here, not left for whatever downstream code
    happens to call datetime.date.fromisoformat() on it (mailchimp_campaign.campaign_title does,
    to build the "(Week N)" tag). Catching it here means a bad date aborts before any network
    call, matching this module's own contract: raise NewsletterMarkdownError before anything
    touches the network, don't guess.
    """
    date = _required_field(r'^\*\*Date:\*\*\s*(.+)$', text, 'Date')
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise NewsletterMarkdownError(f"**Date:** must be YYYY-MM-DD, got {date!r}")
    return date


def _parse_banner(text):
    banner_path = _required_field(r'^\*\*Banner:\*\*\s*(.+)$', text, 'Banner')
    banner_alt = _required_field(r'^\*\*Banner Alt:\*\*\s*(.+)$', text, 'Banner Alt')
    raw_link = _required_field(r'^\*\*Banner Link:\*\*\s*(.+)$', text, 'Banner Link')
    banner_link = None if raw_link == '—' else raw_link
    return banner_path, banner_alt, banner_link


def _parse_intro(text):
    # The heading is bounded to one line and the body ends at the next real H2 ("## " with a
    # space), so a malformed intro can't swallow across a section boundary and quietly parse
    # section 1 as intro body.
    match = re.search(
        r'^## Intro\n+### ([^\n]+)\n+(.+?)\n\n(?=## )',
        text, re.DOTALL | re.MULTILINE,
    )
    if not match:
        raise NewsletterMarkdownError("Could not find ## Intro section")
    title = match.group(1).strip()
    paragraphs = split_paragraphs(match.group(2))
    if not paragraphs:
        raise NewsletterMarkdownError("## Intro has no body paragraphs")
    return title, paragraphs


def _parse_section_block(block):
    match = re.match(
        r'^### (?P<headline>[^\n]+)\n+'
        r'\*\*Source:\*\*\s*(?P<source>.+?)\s*\n+'
        r'(?P<summary>.+)\Z',
        block, re.DOTALL,
    )
    if not match:
        raise NewsletterMarkdownError(
            f"Malformed section block (expected headline, **Source:**, then summary):\n{block[:120]}"
        )
    summary_paragraphs = split_paragraphs(match.group('summary'))
    if not summary_paragraphs:
        raise NewsletterMarkdownError(f"Section '{match.group('headline').strip()}' has no summary text")
    return Section(
        headline=match.group('headline').strip(),
        source=match.group('source').strip(),
        summary_paragraphs=summary_paragraphs,
    )


def _parse_sections(text):
    match = re.search(r'^## This Week\n+(.*?)\n+## Related Reading', text, re.DOTALL | re.MULTILINE)
    if not match:
        raise NewsletterMarkdownError("Could not find ## This Week section")
    blocks = [b.strip() for b in re.split(r'^---\s*$', match.group(1), flags=re.MULTILINE) if b.strip()]
    if len(blocks) != 3:
        raise NewsletterMarkdownError(
            f"## This Week must have exactly 3 section blocks (the template has 3 slots), found {len(blocks)}"
        )
    return [_parse_section_block(block) for block in blocks]


def _parse_related_reading(text):
    match = re.search(r'^## Related Reading\n+(.*?)\n+## Worth Reflecting', text, re.DOTALL | re.MULTILINE)
    if not match:
        raise NewsletterMarkdownError("Could not find ## Related Reading section")
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    links = []
    for line in lines:
        bullet = re.match(r'^-\s+(\[[^\]]+\]\([^)]+\))\s*$', line)
        if not bullet:
            raise NewsletterMarkdownError(
                f"Malformed line in ## Related Reading (expected '- [label](url)'): {line}"
            )
        links.append(bullet.group(1))
    if not (1 <= len(links) <= 5):
        raise NewsletterMarkdownError(f"## Related Reading must have 1-5 links, found {len(links)}")
    return links


def _parse_reflect(text):
    match = re.search(r'^## Worth Reflecting\n+(.*?)\Z', text, re.DOTALL | re.MULTILINE)
    if not match:
        raise NewsletterMarkdownError("Could not find ## Worth Reflecting section")
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    questions = []
    for line in lines:
        bullet = re.match(r'^-\s+(.+)$', line)
        if not bullet:
            raise NewsletterMarkdownError(f"Malformed line in ## Worth Reflecting (expected '- question'): {line}")
        questions.append(bullet.group(1).strip())
    if not (1 <= len(questions) <= 5):
        raise NewsletterMarkdownError(f"## Worth Reflecting must have 1-5 questions, found {len(questions)}")
    return questions


def parse_newsletter_markdown(path) -> ParsedNewsletter:
    """Parse a newsletter markdown file. Raises NewsletterMarkdownError on
    any condition that should abort the run before anything is created.
    """
    text = Path(path).read_text(encoding='utf-8')

    banner_path, banner_alt, banner_link = _parse_banner(text)
    intro_title, intro_paragraphs = _parse_intro(text)

    return ParsedNewsletter(
        subject=_required_field(r'^\*\*Subject:\*\*\s*(.+)$', text, 'Subject'),
        preview_text=_required_field(r'^\*\*Preview Text:\*\*\s*(.+)$', text, 'Preview Text'),
        date=_parse_date(text),
        banner_path=banner_path,
        banner_alt=banner_alt,
        banner_link=banner_link,
        intro_title=intro_title,
        intro_paragraphs=intro_paragraphs,
        sections=_parse_sections(text),
        related_reading_links=_parse_related_reading(text),
        reflect_questions=_parse_reflect(text),
    )
