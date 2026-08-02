"""Patch the template, create the campaign, write its text sections, and verify the result
against the re-fetched rendered html.

Everything here that isn't a generic client verb or the banner upload (that's
mailchimp_assets.py) lives in this module. No send, test-send, resume, or schedule call is ever
made -- the client's own tripwire enforces that regardless of anything in this module.
"""

import datetime
import re
from typing import Dict, Optional, Tuple

from mailchimp_client import MailchimpAPIError, MailchimpClient
from newsletter_markdown import ParsedNewsletter
from newsletter_renderer import escape_text, render_paragraph
from template_patcher import escape_attr


class CampaignError(RuntimeError):
    """Raised when the post-write verification against the rendered html
    finds something that doesn't match what was just pushed. A 200 from the
    write calls is not a fidelity signal -- region content can't be read
    back, so this is the only check that catches a silently-discarded write.
    """


class LiveTemplateUnhealthyError(CampaignError):
    """Raised by check_live_template_health, and only by it. A distinct
    subclass rather than a bare CampaignError so push.py's error handling
    doesn't have to guess: every other CampaignError fires after the
    campaign draft already exists in Mailchimp, but this one fires first,
    before any upload or write -- conflating the two would tell the user to
    go check a draft that was never created.
    """


def check_live_template_health(client: MailchimpClient, template_id: int) -> None:
    """Preflight gate for --live-template only -- the throwaway path doesn't
    touch a pre-existing template at all, so nothing here applies to it.
    Runs before any upload or write.

    A live template can end up broken (deleted via the Mailchimp web UI, or
    reverted to a drag-and-drop template) entirely outside this tool, so
    nothing else would notice before PATCHing a template that no longer
    accepts section writes. See API-NOTES.md for what each failure means.

    Never a GET-then-assume-alive check: a deleted template stays fetchable
    by its exact id as a tombstone (active=False) -- exactly the shape this
    function is built to catch.
    """
    try:
        template = client.get(f'/templates/{template_id}', params={
            'fields': 'id,active,drag_and_drop',
        })
    except MailchimpAPIError as e:
        raise LiveTemplateUnhealthyError(
            f'Live template {template_id} could not be fetched ({e}). It may have been '
            f'deleted -- see API-NOTES.md.'
        )
    if template.get('active') is False:
        raise LiveTemplateUnhealthyError(
            f'Live template {template_id} is inactive (active=False) -- it was likely '
            f'deleted. See API-NOTES.md.'
        )
    if template.get('drag_and_drop') is True:
        raise LiveTemplateUnhealthyError(
            f'Live template {template_id} has drag_and_drop=True -- section writes will '
            f'not work against it. See API-NOTES.md.'
        )


def push_template(
    client: MailchimpClient,
    html: str,
    *,
    template_id: Optional[int] = None,
    throwaway_name: Optional[str] = None,
) -> int:
    """PATCH an existing template (--live-template) or POST a brand-new
    throwaway one (the default) -- never both, and never neither. `PATCH
    /templates/{id}` re-derives every mc:edit region from the html it's
    given; `POST /templates` creates a new one the same way.
    """
    if (template_id is None) == (throwaway_name is None):
        raise ValueError('Exactly one of template_id or throwaway_name is required')
    if template_id is not None:
        client.patch(f'/templates/{template_id}', {'html': html})
        return template_id
    result = client.post('/templates', {'name': throwaway_name, 'html': html})
    return result['id']


def _iso_week(service_date: str) -> int:
    """ISO week of a YYYY-MM-DD date -- used only to build the campaign
    title's "(Week N)" tag.
    """
    return datetime.date.fromisoformat(service_date).isocalendar()[1]


def campaign_title(parsed: ParsedNewsletter, *, throwaway: bool = False) -> str:
    """Build the campaign title: "<subject> (Week N)", with a trailing 🔍
    for a throwaway run.

    🔍 marks throwaways that are safe to delete -- delete_campaign_if_throwaway
    checks for it before any DELETE call, so writing it here is load-bearing.
    """
    marker = ' 🔍' if throwaway else ''
    return f'{parsed.subject} (Week {_iso_week(parsed.date)}){marker}'


def create_campaign(
    client: MailchimpClient, *, template_id: int, parsed: ParsedNewsletter,
    audience_id: str, from_name: str, reply_to: str, throwaway: bool = False,
) -> Tuple[str, Optional[str]]:
    """POST /campaigns. Returns (campaign_id, web_id) -- the two are
    different numbers; web_id is what the editor URL uses, campaign_id is
    what every other API call needs.

    `throwaway=True` adds the 🔍 marker to the title, which is what gates
    deletion via delete_campaign_if_throwaway.
    """
    payload = {
        'type': 'regular',
        'recipients': {'list_id': audience_id},
        'settings': {
            'subject_line': parsed.subject,
            'preview_text': parsed.preview_text,
            'title': campaign_title(parsed, throwaway=throwaway),
            'from_name': from_name,
            'reply_to': reply_to,
            'template_id': template_id,
        },
    }
    result = client.post('/campaigns', payload)
    return result['id'], result.get('web_id')


def delete_campaign_if_throwaway(client: MailchimpClient, campaign_id: str) -> None:
    """Delete a campaign only when its title contains 🔍 (the throwaway
    marker). Refuses otherwise, so this tool can never delete a real
    campaign or a hand-built one.

    Writing 🔍 into throwaway titles at creation (campaign_title with
    throwaway=True) is therefore a hard dependency of this guard -- if the
    title was never written with 🔍, this function will always refuse.

    Also refuses a campaign at status 'schedule', marker or no marker: this
    tool never asks Mailchimp to schedule anything, so a scheduled campaign
    -- throwaway or not -- is never this tool's to delete out from under
    whatever schedule the human set.
    """
    campaign = client.get(f'/campaigns/{campaign_id}')
    title = campaign.get('settings', {}).get('title', '')
    status = campaign.get('status')
    if status == 'schedule':
        raise CampaignError(
            f'Refusing to delete campaign {campaign_id}: status is "schedule". '
            f'This tool never schedules and never deletes a scheduled campaign -- '
            f'unschedule it first (in the Mailchimp editor) if it truly is a throwaway.'
        )
    if '🔍' not in title:
        raise CampaignError(
            f'Refusing to delete campaign {campaign_id}: title does not contain 🔍 '
            f'(title: {title!r}). Only throwaway campaigns may be deleted by this tool.'
        )
    client.delete(f'/campaigns/{campaign_id}')


def write_sections(client: MailchimpClient, campaign_id: str, template_id: int, regions: Dict[str, str]) -> None:
    """PUT /campaigns/{id}/content with template.sections -- surgical,
    untargeted regions do not move. Never a bare 'html' key: see
    mailchimp_client.py and API-NOTES.md -- that returns 200 and wipes the
    campaign body.
    """
    client.put(f'/campaigns/{campaign_id}/content', {
        'template': {'id': template_id, 'sections': regions},
    })


def fetch_rendered_html(client: MailchimpClient, campaign_id: str) -> str:
    """Region content can't be read back -- `GET /campaigns/{id}/content`
    carries no `template` key -- so verification is always against the
    rendered `html`.
    """
    content = client.get(f'/campaigns/{campaign_id}/content')
    return content.get('html', '')


def _body_text_present(text: str, html: str) -> bool:
    """Is this exact string present in the rendered html?

    A single-form check, not a tolerance -- the caller is responsible for passing `text` through
    whatever transform newsletter_renderer applied before writing it: render_paragraph's output
    (already escaped and markdown-converted) for a summary/intro/question, or escape_text(...) for
    a raw heading/headline/attribution string that only went through escape_text, not the full
    format_text pipeline. Before the renderer escaped all inserted text canonically, this checked
    both the raw and escape_attr-escaped forms as a tolerance for an unescaped ampersand; that
    tolerance is gone now that there's one canonical escaping to compare against.
    """
    return text in html


_HREF_ATTR_RE = re.compile(r'href="([^"]*)"')


def _href_relaxed(fragment: str) -> str:
    """The href-ampersand-relaxed variant of a rendered fragment: '&amp;' -> '&', but only inside
    href="..." attribute values, everywhere else in `fragment` untouched.

    Confirmed via a live push (a link URL with a query-string ampersand): Mailchimp's stored/
    rendered html normalizes '&amp;' back to a bare '&' inside href attribute values specifically
    -- this tool still *writes* escape_attr(url) (the correct, safe value; a bare '&' in the write
    payload risks the same double-decode ambiguity escape_attr exists to avoid), but the rendered
    html this function checks against reflects Mailchimp's own normalization, not what was sent.
    Every other character this tool escapes (plain-text '&', '<', '>', the '&lt;'/'&gt;' around a
    literal '<em>' in body text) survived unchanged in the same live push, so the relaxation is
    scoped to href attribute values only -- see API-NOTES.md.
    """
    return _HREF_ATTR_RE.sub(lambda m: f'href="{m.group(1).replace("&amp;", "&")}"', fragment)


def _rendered_paragraph_present(paragraph: str, html: str) -> bool:
    """render_paragraph(paragraph) presence check, tolerant of Mailchimp's href-ampersand
    normalization (see _href_relaxed) -- the one narrow exception to _body_text_present's
    single-form rule, and only for content that can contain a markdown link.
    """
    rendered = render_paragraph(paragraph)
    return _body_text_present(rendered, html) or _body_text_present(_href_relaxed(rendered), html)


def verify_rendered_html(html: str, parsed: ParsedNewsletter, banner_url: Optional[str]) -> None:
    """Assert the rendered campaign actually carries this run's content.
    Raises CampaignError naming every problem found, not just the first --
    a silently unmatched write is the most likely bug in this stage.

    Banner alt/href are compared through escape_attr, the same function the
    patcher writes them with. Banner checks only run when `banner_url` was
    actually patched (i.e. not --no-images) -- the image region carries
    mc:edit on the <img> itself, so the rendered html is the only place a
    silently no-op'd banner patch could ever be caught.

    Body text (summaries, questions) goes through render_paragraph before comparison, since
    that's the full transform (escaping, links, bold, bullets) the renderer applies. A raw
    heading/headline/attribution string only ever goes through escape_text (no markdown support),
    so it's compared through that instead -- see _body_text_present and newsletter_renderer.escape_text.
    """
    problems = []
    if banner_url is not None:
        if banner_url not in html:
            problems.append('banner image URL not found in rendered html')
        banner_alt = escape_attr(parsed.banner_alt)
        if banner_alt not in html:
            problems.append('banner alt text not found in rendered html')
        expected_href = escape_attr(parsed.banner_link or '#')
        if expected_href not in html:
            problems.append('banner href not found in rendered html')
    if not _body_text_present(escape_text(parsed.intro_title), html):
        problems.append('intro title not found in rendered html')
    for paragraph in parsed.intro_paragraphs:
        # Intro paragraphs go through the same markdown (links/bold/bullets) transform as section
        # summaries before they reach Mailchimp -- check against that, not the raw markdown.
        if not _rendered_paragraph_present(paragraph, html):
            problems.append('an intro paragraph not found in rendered html')
    for section in parsed.sections:
        if not _body_text_present(escape_text(section.headline), html):
            problems.append(f'section headline not found in rendered html: {section.headline!r}')
        attribution = f'<em>via {escape_text(section.source)}</em>'
        if not _body_text_present(attribution, html):
            problems.append(f'section attribution not found in rendered html: {section.headline!r}')
        for paragraph in section.summary_paragraphs:
            # Summary paragraphs may carry markdown [label](url) links, or be a bullet block --
            # the renderer converts both before they reach Mailchimp, so the raw markdown text
            # itself is never what's in the rendered html; check against the same transformation.
            if not _rendered_paragraph_present(paragraph, html):
                problems.append(f'a summary paragraph not found in rendered html ({section.headline!r})')
    for question in parsed.reflect_questions:
        if not _rendered_paragraph_present(question, html):
            problems.append('a Worth Reflecting question not found in rendered html')
    if problems:
        raise CampaignError('Post-write verification failed:\n  ' + '\n  '.join(problems))
