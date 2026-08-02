#!/usr/bin/env python3
"""Stage 2: push a newsletter markdown file to a Mailchimp campaign draft.

The write order is fixed and not negotiable -- see AGENTS.md and API-NOTES.md:

    preflight -> upload banner -> patch template copy -> POST/PATCH template
    -> POST campaign -> PUT sections -> verify

Preflight (the banner file, unless --no-images) raises before any *write* -- but with --live-template,
check_live_template_health runs first of all, and it is itself a network call (a GET on the live
template, to catch a deleted or drag-and-drop template before anything is uploaded or patched).

This script never sends, schedules, resumes, or test-sends a campaign. It creates a draft; a
human reviews it in Mailchimp and sends it by hand.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from mailchimp_assets import AssetError, preflight_banner, upload_asset
from mailchimp_campaign import (
    CampaignError,
    LiveTemplateUnhealthyError,
    check_live_template_health,
    create_campaign,
    delete_campaign_if_throwaway,
    fetch_rendered_html,
    push_template,
    verify_rendered_html,
    write_sections,
)
from mailchimp_client import MailchimpAPIError, MailchimpClient
from newsletter_markdown import NewsletterMarkdownError, ParsedNewsletter, parse_newsletter_markdown
from newsletter_renderer import render_regions
from template_patcher import TemplatePatchError, patch_template

SCRIPT_DIR = Path(__file__).parent
DEFAULT_MARKDOWN_PATH = SCRIPT_DIR / 'sample' / 'newsletter-2026-08-02.md'
TEMPLATE_PATH = SCRIPT_DIR / 'template.html'


def load_template_source() -> str:
    """Always the generator's own output (template.html), never a template
    Mailchimp has stored -- see template_patcher.py and API-NOTES.md.
    """
    return TEMPLATE_PATH.read_text(encoding='utf-8')


def resolve_audience_id(client: MailchimpClient) -> str:
    """MAILCHIMP_AUDIENCE_ID from .env when set; otherwise the one-call
    lookup: GET /lists. Exactly one audience -> use it and say so. Otherwise
    print every audience id/name and exit, telling the user to set the
    variable.
    """
    env_value = os.getenv('MAILCHIMP_AUDIENCE_ID')
    if env_value:
        return env_value
    result = client.get('/lists', params={'fields': 'lists.id,lists.name,total_items'})
    lists = result.get('lists', [])
    if len(lists) == 1:
        audience = lists[0]
        print(f"MAILCHIMP_AUDIENCE_ID not set -- using the only audience in this account: "
              f"{audience['id']} ({audience['name']})")
        return audience['id']
    if not lists:
        sys.exit('MAILCHIMP_AUDIENCE_ID is not set in .env, and this account has no audiences yet '
                  '-- create one (Audience -> Create Audience in Mailchimp) before running push.py.')
    print('MAILCHIMP_AUDIENCE_ID is not set in .env, and this account has '
          f'{len(lists)} audiences -- set MAILCHIMP_AUDIENCE_ID to one of:')
    for audience in lists:
        print(f"  {audience['id']}  {audience['name']}")
    sys.exit(1)


def run(
    parsed: ParsedNewsletter,
    markdown_dir: Path,
    client: MailchimpClient,
    *,
    template_id=None,
    throwaway_template_name=None,
    audience_id: str,
    from_name: str,
    reply_to: str,
    no_images: bool = False,
) -> dict:
    """Everything Stage 2 owns, in the fixed order. Returns a report dict:
    campaign_id, web_id, template_id, banner_url.

    Exactly one of template_id / throwaway_template_name must be given -- see
    mailchimp_campaign.push_template.
    """
    if template_id is not None:
        check_live_template_health(client, template_id)

    is_throwaway = throwaway_template_name is not None

    banner_url = None
    if not no_images:
        banner_path = preflight_banner(parsed, markdown_dir)
        banner_url = upload_asset(client, banner_path)

    if template_id is not None and no_images:
        # --live-template + --no-images: leave the live template's stored html completely
        # untouched -- no load_template_source, no patch_template, no push_template. Before this
        # branch existed, this combination still loaded template.html (with its *placeholder*
        # banner) and PATCHed the whole thing over the live template, silently replacing the live
        # template's real banner with the placeholder -- exactly what --no-images promises not to
        # do. The throwaway path's --no-images meaning is unchanged: a brand-new template still
        # ships with the placeholder banner there, since there's no live template to leave alone.
        used_template_id = template_id
    else:
        html = load_template_source()
        patched_html = patch_template(html, parsed, banner_url, patch_images=not no_images)
        used_template_id = push_template(
            client, patched_html,
            template_id=template_id, throwaway_name=throwaway_template_name,
        )

    campaign_id, web_id = create_campaign(
        client, template_id=used_template_id, parsed=parsed,
        audience_id=audience_id, from_name=from_name, reply_to=reply_to,
        throwaway=is_throwaway,
    )
    # Printed immediately, not just in the final report -- if write_sections or the verify fetch
    # below raises, this is the only record that a draft already exists and needs a look.
    print(f'Campaign created: campaign_id={campaign_id} web_id={web_id}')

    regions = render_regions(parsed)
    write_sections(client, campaign_id, used_template_id, regions)

    rendered_html = fetch_rendered_html(client, campaign_id)
    verify_rendered_html(rendered_html, parsed, banner_url)

    return {
        'campaign_id': campaign_id,
        'web_id': web_id,
        'template_id': used_template_id,
        'banner_url': banner_url,
    }


def run_dry(parsed: ParsedNewsletter, markdown_dir: Path, *, no_images: bool) -> None:
    """Dry run: render and inspect locally, touching nothing remote. Prints
    what would be uploaded and written; no network calls whatsoever.

    Exits non-zero if the banner fails preflight (unless --no-images) -- missing, or in violation
    of FORMAT.md's containment contract (an absolute path, or one that resolves outside the
    markdown file's own directory) -- a real run hard-fails on exactly these conditions at
    preflight, and a dry run that reports the problem but still exits 0 would contradict the
    promise that --dry-run catches problems before any network call. Routing through
    preflight_banner (the same function the real run calls) rather than a separate ad hoc check
    here is what keeps the two paths agreeing on what counts as a problem. The full report is
    still printed first; the exit is a verdict on top of it, not a replacement for it.
    """
    print('DRY RUN -- nothing will be uploaded or created in Mailchimp\n')

    print('Regions that would be written:')
    for name, html in render_regions(parsed).items():
        print(f'  {name}: {len(html)} chars')

    print('\nBanner:')
    banner_error = None
    if no_images:
        print('  (--no-images: template keeps its current banner)')
    else:
        try:
            banner_path = preflight_banner(parsed, markdown_dir)
            print(f'  {banner_path} (exists) -- would upload and patch into the template')
        except AssetError as e:
            banner_error = e
            print(f'  {markdown_dir / parsed.banner_path} -- PROBLEM: {e}')

    if banner_error:
        sys.exit(f'\nDry run found a problem: {banner_error}')

    print('\nDry run complete. No campaign was created.')


def _print_final_report(client: MailchimpClient, result: dict, *, no_open: bool) -> None:
    # campaign_id/web_id already printed once, immediately after create_campaign in run() --
    # not repeated here to avoid a duplicate line; this report picks up from there.
    dc = client.dc
    print()
    print(f"Template used: {result['template_id']}")
    if result['banner_url']:
        print(f"Banner -> {result['banner_url']}")
    print()
    print('This script never sends. Review the draft in Mailchimp; schedule it there yourself.')

    if result.get('web_id'):
        url = f'https://{dc}.admin.mailchimp.com/campaigns/edit?id={result["web_id"]}'
        if no_open:
            print(f'Editor URL: {url}')
        else:
            try:
                subprocess.run(['open', url], check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                print(f'Open the campaign in Mailchimp: {url}')


def main():
    parser = argparse.ArgumentParser(description='Stage 2: push a newsletter markdown file to a Mailchimp draft')
    parser.add_argument('markdown_path', nargs='?', default=str(DEFAULT_MARKDOWN_PATH),
                        help=f'Path to the newsletter markdown file (default: {DEFAULT_MARKDOWN_PATH})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Render locally; touch nothing remote')
    parser.add_argument('--no-images', action='store_true',
                        help='Skip the banner upload. With --live-template, also skips the template '
                             'PATCH entirely -- the live template is left fully untouched. Without '
                             '--live-template (throwaway), the new template still ships with the '
                             "generator's placeholder banner.")
    parser.add_argument('--live-template', metavar='TEMPLATE_ID',
                        help='PATCH an existing template by id instead of creating a throwaway copy')
    parser.add_argument('--throwaway-template-name',
                        help='Name for the throwaway template (used unless --live-template is given)')
    parser.add_argument('--no-open', action='store_true',
                        help='Suppress opening the campaign edit URL in the browser')
    parser.add_argument('--delete-throwaway', metavar='CAMPAIGN_ID',
                        help='Delete a throwaway campaign (title must contain the 🔍 marker, '
                             'status must not be "schedule"). Does nothing else.')
    args = parser.parse_args()

    if args.delete_throwaway and args.dry_run:
        parser.error('--delete-throwaway and --dry-run cannot be used together')

    load_dotenv(SCRIPT_DIR / '.env')

    # Checked before touching the markdown_path at all -- a delete needs no markdown file, and
    # positional's default ('sample/newsletter-2026-08-02.md' unless a path was also given)
    # shouldn't be able to abort a delete over an unrelated parse error.
    if args.delete_throwaway:
        try:
            client = MailchimpClient()
        except RuntimeError as e:
            sys.exit(str(e))
        try:
            delete_campaign_if_throwaway(client, args.delete_throwaway)
        except CampaignError as e:
            sys.exit(f'Delete failed: {e}')
        except MailchimpAPIError as e:
            sys.exit(f'Mailchimp API error: {e}')
        print(f'Deleted throwaway campaign {args.delete_throwaway}.')
        return

    md_path = Path(args.markdown_path)

    try:
        parsed = parse_newsletter_markdown(md_path)
    except NewsletterMarkdownError as e:
        sys.exit(f'Error parsing {md_path}: {e}')

    if args.dry_run:
        run_dry(parsed, md_path.parent, no_images=args.no_images)
        return

    # MailchimpClient.__init__ raises a plain RuntimeError (no API key, or a key with no
    # data-center suffix) -- the most common fresh-clone mistake, so it gets the same clean
    # sys.exit treatment as every other anticipated failure below, not a raw traceback.
    try:
        client = MailchimpClient()
    except RuntimeError as e:
        sys.exit(str(e))

    from_name = os.getenv('MAILCHIMP_FROM_NAME')
    reply_to = os.getenv('MAILCHIMP_REPLY_TO')
    if not from_name:
        sys.exit('MAILCHIMP_FROM_NAME not set in .env -- Mailchimp rejects a campaign without one')
    if not reply_to:
        sys.exit('MAILCHIMP_REPLY_TO not set in .env -- Mailchimp rejects a campaign without one')

    kwargs = {
        'no_images': args.no_images,
        'audience_id': resolve_audience_id(client),
        'from_name': from_name,
        'reply_to': reply_to,
    }
    if args.live_template:
        try:
            kwargs['template_id'] = int(args.live_template)
        except ValueError:
            parser.error(f'--live-template must be a numeric template id, got {args.live_template!r}')
    else:
        kwargs['throwaway_template_name'] = args.throwaway_template_name or f'newsletter-check-{parsed.date}'

    try:
        result = run(parsed, md_path.parent, client, **kwargs)
    except AssetError as e:
        sys.exit(f'Aborted: {e}')
    except TemplatePatchError as e:
        sys.exit(f'Template patch failed: {e}')
    except LiveTemplateUnhealthyError as e:
        # Raised by check_live_template_health, which runs first -- nothing was uploaded or
        # written this run. Must be caught ahead of the bare CampaignError branch below (it's a
        # subclass): that branch's message claims a draft was created, which isn't true here.
        sys.exit(f'Aborted: {e}')
    except CampaignError as e:
        # Raised by verify_rendered_html, which runs last -- the campaign draft and its sections
        # already exist in Mailchimp by this point. Not a traceback-worthy crash; a report to
        # act on.
        sys.exit(f'{e}\n\nThe campaign draft was created but failed verification -- check it in Mailchimp.')
    except MailchimpAPIError as e:
        # Can fire before or after create_campaign succeeds (it's also raised by write_sections
        # and the verify fetch) -- unlike the CampaignError branch above, this one can't tell
        # which. run() prints "Campaign created: campaign_id=..." immediately once one exists, so
        # that line's presence or absence above this error is the real signal.
        sys.exit(f'Mailchimp API error: {e}\n\n'
                  f'If "Campaign created: campaign_id=..." was printed above, that draft exists '
                  f'in Mailchimp and needs a look. If not, nothing was created.')

    _print_final_report(client, result, no_open=args.no_open)


if __name__ == '__main__':
    main()
