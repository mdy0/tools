"""Patch the banner mc:edit region of a copy of template.html with the uploaded banner image.

Pure function on an HTML string -- no network, no file I/O. The caller loads template.html
itself and passes its contents in; this module never opens that file and must never be pointed at
it for writing -- push.py patches a copy, never the committed source.

The banner region carries mc:edit on the <img> itself, which is the only way to get a real Image
content block in the legacy builder -- and which makes it invisible to the API once a campaign
exists (see API-NOTES.md). That is why this substitution happens on the template, before a
campaign is ever created, rather than as a later API write.
"""

import re
from typing import Optional

from newsletter_markdown import ParsedNewsletter


class TemplatePatchError(ValueError):
    """Raised when the named mc:edit region can't be found in the template --
    a silently unmatched substitution is the most likely bug here, so a miss
    is a hard error rather than a no-op.
    """


def escape_attr(value: str) -> str:
    """Escape a value going into a double-quoted HTML attribute. `alt` and
    `href` are the only two attributes this module writes with data it
    doesn't control (the markdown's banner alt/link) -- a literal `"` in
    either closes the attribute early and corrupts the tag, and the next
    patch run then can't match it at all. `src` is generated from a
    Mailchimp upload response, never hand-typed, so it isn't escaped here.

    Public: mailchimp_campaign.verify_rendered_html must compare against
    exactly this escaping -- a title/alt containing `&`, `<` or `"` is
    escaped by the patcher, and the verify step re-fetches the live HTML and
    must apply the same transform or it false-fails against a campaign that
    was actually patched correctly.
    """
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')


def _image_region_pattern(region: str) -> re.Pattern:
    # Matches the whole <a href="...">...<img ... src="..." ... alt="..." ...
    # mc:edit="{region}"...></a> element, in the attribute order make_template.py emits (href on
    # the <a>; src before alt on the <img>; anything else -- width, style -- may sit between alt
    # and mc:edit).
    return re.compile(
        r'(<a href=")([^"]*)("[^>]*>\s*<img[^>]*\bsrc=")([^"]*)'
        r'("[^>]*\balt=")([^"]*)('
        rf'"[^>]*\bmc:edit="{re.escape(region)}"[^>]*>\s*</a>)',
        re.DOTALL,
    )


def _replace_image_region(html: str, region: str, *, src: str, alt: str, href: str) -> str:
    match = _image_region_pattern(region).search(html)
    if not match:
        raise TemplatePatchError(f'Could not find an image region for mc:edit="{region}"')
    replacement = (
        match.group(1) + escape_attr(href) + match.group(3) + src
        + match.group(5) + escape_attr(alt) + match.group(7)
    )
    return html[:match.start()] + replacement + html[match.end():]


def patch_banner(html: str, src: str, alt: str, href: Optional[str]) -> str:
    """Set src, alt and the wrapping href on the banner region, all three
    together. template.html always has the <a> wrapper; `href=None` (the
    markdown's `**Banner Link:** —`) writes `href="#"` -- the Mailchimp-
    neutral "not linked" value, since a bare <img> with no <a> ancestor is
    not a shape this template offers.
    """
    return _replace_image_region(html, 'banner', src=src, alt=alt, href=href or '#')


def patch_template(html: str, parsed: ParsedNewsletter, banner_url: str, *, patch_images: bool = True) -> str:
    """Convenience wrapper for one run's template patching. `patch_images=False` is --no-images'
    contract: leave the template's placeholder banner exactly as-is.
    """
    if not patch_images:
        return html
    return patch_banner(html, banner_url, parsed.banner_alt, parsed.banner_link)
