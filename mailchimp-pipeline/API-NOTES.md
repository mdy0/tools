# API-NOTES.md — Mailchimp Marketing API facts that aren't in the official docs

This is a distilled, sanitized digest of things learned the hard way, through direct experimentation against a live Mailchimp account. None of it is theoretical, and most of it either isn't in Mailchimp's own documentation or is actively contradicted by it. Every concrete id, count, and account fact below has been replaced by the generic fact it evidences.

For the how-to version of the `mc:edit`/`mc:hideable` markup rules below — what to write, not why — see [docs/editable-regions.md](docs/editable-regions.md).

## Classic (legacy) builder vs. the new builder

Everything below applies to the **classic/legacy coded-template API path** — the one Mailchimp's docs call, inconsistently, "the classic builder" or just leave undistinguished from the newer drag-and-drop builder. This tool creates campaigns from a coded (`mc:edit`-region) template using `POST /templates`, which always returns `drag_and_drop: false`. A drag-and-drop template behaves completely differently under the API (see below) and the official docs do not call out which rules apply to which builder. If `drag_and_drop` ever comes back `true` for a template you're patching, stop — section writes will not work against it.

Drag-and-drop templates are unreachable from the API for creation purposes: `POST /templates` always produces a coded (classic) template, never a drag-and-drop one. A drag-and-drop template's `GET /templates/{id}/default-content` returns zero sections, which would cost this tool's entire write path if it ever pointed there by mistake.

## The `html` key silently wipes a campaign

`PUT /campaigns/{id}/content` with a top-level `html` key returns **HTTP 200** and silently discards whatever markup you sent, resetting the campaign body to the base template's defaults. This has destroyed a real campaign in testing. The only safe write is the sections form: `{'template': {'id': ..., 'sections': {...}}}`. `mailchimp_client.py` doesn't special-case the path — the discipline is "never build that payload," enforced by `mailchimp_campaign.write_sections` being the only function that PUTs campaign content, and it never accepts an `html` key.

## Verify after every write — a 200 is not a fidelity signal

`GET /campaigns/{id}/content` never carries a `template` key for any campaign — region content cannot be read back. The only way to confirm a write actually landed is to `GET` the campaign's **rendered** `html` (same endpoint, no `template` key requested) and check that the content you just pushed appears in it. This is why `push.py` always ends with `verify_rendered_html` — a silently-discarded or partially-applied write is otherwise invisible.

## Image regions: the central trap

- The **only** content type reachable via the coded-template API is **Image**, and only by putting `mc:edit` directly on the `<img>` tag itself, with **no `mc:edit` on any ancestor**. An `mc:edit` region on a wrapping `<a>` or `<td>` — even one level up — silently suppresses the Image content type on the `<img>` below it. It still renders as *something* (a generic Editable Region) but loses Replace/Alt/Link entirely, and a sections write to it is silently ignored.
- **Image regions are invisible to the API once a campaign exists.** `GET /templates/{id}/default-content` strips them out entirely, and a `PUT /campaigns/{id}/content` sections write to an image region's name is a no-op — HTTP 200, nothing changes. This is *why* the write order in this tool is fixed: upload the image → patch it into a **copy of the template** → create the campaign from that template → then write text sections. There is no way to fix a draft's images after the fact via the API; the only recovery is a new draft from a correctly-patched template.
- **A sections payload containing `mc:edit` anywhere in its value is discarded wholesale** — not just the offending region, the entire write for that call. Writing a region whose value contains a nested `<img mc:edit="...">` returns 200 and changes nothing. The renderer in this tool never emits `mc:edit` in region content for exactly this reason.
- **Replacing an image by hand in the Mailchimp editor wipes its `alt` text** (and `width`). Mailchimp rewrites the whole `<img>` tag on Replace. If `alt` carries content that matters (a headline, a title), set it again *after* replacing, never before — or better, patch `src` and `alt` together via the template before the campaign exists, which is what this tool always does.

## Editor-pane rendering rules (why the renderer looks the way it does)

Content that is technically valid HTML can still render as a **blank editing pane** in the classic builder, even though the same content shows up fine in the HTML/code view and in the sent email. Confirmed rendering rules, from direct testing:

- A `<p style="...">` block renders blank in the editor pane. A `<h2>`/heading element with nested styled `<span>`s renders correctly. A styled `<div>` per paragraph, `<br><br>`-joined, renders correctly and keeps its styling.
- A styled `<a>` — with or without `target`, with a nested `<span>`, or with the font moved onto its own `style` attribute — has its **link text dropped** in the pane (though the underlying HTML still has it). Only a **bare** `<a href="..." target="_blank">label</a>`, with no `style` anywhere on it, reliably keeps its text and stays editable.
- **The template's own stylesheet can eat link text in the pane**, independent of the block markup — this was the hardest of these bugs to isolate, because the exact same block markup renders correctly in a clean document and fails inside the full template. The fix that actually works: keep the whole stylesheet (deleting the layout rules causes real visual regressions), but strip every CSS selector that **names an anchor** (`a`, `a:hover`, `.foo a`, etc.) — rules with a mixed selector list keep everything except the anchor part. This is a superset of every narrower fix tried and it costs nothing visually, because the rules being stripped are Outlook/iOS hacks and a link color the mail client supplies anyway. `make_template.py`'s self-check enforces this: it refuses to write a template whose stylesheet contains an anchor-naming selector.
- **A `border-collapse: separate` wrapper table needs `border-spacing: 0` explicitly**, or it picks up the browser's default (commonly 2px) on every cell, which is enough to visibly misalign a heading against the image below it. This template sidesteps the issue with `border-collapse: collapse` on its wrapper table instead (which has no `border-spacing` concept at all) — this bullet is background knowledge from a design that used `separate`, not a setting you'll find anywhere in `make_template.py`. Worth knowing if you ever switch this template's layout to `separate` (e.g. for rounded corners, which `collapse` can't do).

None of this affects the *sent* email — it's purely about whether the WYSIWYG editing pane in the Mailchimp UI can display and edit a region by hand. A human never touching the editor pane wouldn't hit any of it; it matters here because a coded template that's API-writable but unusable by hand defeats half the point of using the classic builder at all.

## Stored href attributes get their `&amp;` normalized back to a bare `&`

A section-content write containing a body-text link (a plain `<a href="...">` inside a text
region, not the banner's `mc:edit`-on-`<img>` region) with a query-string ampersand in its URL --
`href="https://example.com/?a=1&amp;b=2"`, the correct, safely-escaped value to write -- comes back
from `GET /campaigns/{id}/content`'s rendered `html` with that same attribute holding a bare `&`
instead: `href="https://example.com/?a=1&b=2"`. Confirmed via a live push; nothing else this tool
escapes was affected in the same test — plain-text `&`, `<`, `>`, and a literal `<em>` written as
escaped text all survived unchanged. Write the escaped value regardless (a bare `&` in the write
payload is the same double-decode ambiguity `escape_attr` exists to avoid) — this is purely a
render-side normalization to account for when comparing rendered html against expected content;
`mailchimp_campaign._href_relaxed` does this narrowly, only inside `href="..."` values, for exactly
this reason.

## `mc:hideable` and hidden-block removal

Adding `mc:hideable` to a wrapping element (with **no** `mc:edit` on it — a region on an ancestor would suppress an image region beneath it) gives the editor a hide control; clicking it genuinely removes that block from the sent HTML, not just `display:none`s it — confirmed by checking that the block's identifying content is fully absent from both `html` and `archive_html` afterward.

**Caveat**: Mailchimp normally regenerates the plain-text alternative at send time from the current HTML, so a hidden block is normally absent there too — but if the plain-text version is ever hand-edited or frozen, hidden content can leak into it. Worth a check before sending if a block was hidden and the plain-text tab was ever touched by hand.

This tool's generic template doesn't use `mc:hideable` (the demo has no optional blocks to hide), but the mechanism is worth knowing if you add one when adapting this template.

## File Manager facts

- There is **no search-by-name endpoint**. Any name-based lookup has to page through the full file list (`GET /file-manager/files`, offset/count) and filter client-side.
- Re-uploading under a name that's already taken does **not** overwrite — Mailchimp assigns the next available suffixed name, `stem.01.ext`, `stem.02.ext`, etc. A "does this already exist" check has to search the whole suffix family, not just the exact original name, or it will never converge on whichever copy actually has the current bytes. `mailchimp_client.find_files_by_stem` does this.
- A reuse check should compare file **size** as the identity signal for "is this the same upload." Byte-identical re-uploads are common on a re-run; matching by size before falling back to a fresh upload keeps the account from growing by one file per re-run.
- Stale entries are not deleted automatically by this tool, and shouldn't be deleted casually by hand either: date-stamped filenames may still be referenced by an already-created (or already-sent) campaign, and deleting the file breaks the image wherever it's referenced.

## Template facts

- Drag-and-drop templates cannot be created via the API — `POST /templates` always yields a coded (classic) one. This is why the coded-template approach exists at all for API-driven campaigns.
- **`DELETE /templates/{id}` truly removes it** — it drops out of `GET /templates`'s list and out of `total_items`. But a deleted template **stays fetchable by its exact id as a tombstone** (`active: false`). Never treat a successful `GET /templates/{id}` as proof a template exists — check `active: false` on it, or a fetch failure outright (a template can also be gone in a way that 404s instead of tombstoning, depending on how it was removed). This tool's `check_live_template_health` (used only with `--live-template`) does a single `GET /templates/{id}` — not a list call — and treats a failed fetch, `active: false`, or `drag_and_drop: true` on that response as unhealthy, before doing anything else.
- Mailchimp's own editor can bump a template's `date_edited` on a no-op save (opening it and clicking Save without changing anything) — a changed `date_edited` alone is never proof of changed content.

## Campaign facts

- **`web_id` (the number in the editor URL) is not the same value as the API `campaign_id`.** `web_id` is what `https://{dc}.admin.mailchimp.com/campaigns/edit?id={web_id}` needs; every other API call needs `campaign_id`. Don't assume you can use one where the other is expected.
- **`_links` in a campaign response proves nothing about what the campaign will actually accept.** It's been observed byte-identical across draft/scheduled/sent states, advertising actions like `send` and `resume` even on a plain draft, and never listing `schedule`/`unschedule` even on an already-scheduled campaign. Use the campaign's `status` field for state, the documented endpoint shapes for what exists, and your own client-side guard (see AGENTS.md) for what's permitted.
- Send times must land on a quarter-hour boundary (`:00/:15/:30/:45`) in UTC — this tool never schedules anything, but if you're reading a campaign's `send_time` for any reason, that's the granularity Mailchimp enforces.
- **The branded `campaign-archive.com` URL is assigned on scheduling, not sending.** A draft's public archive page exists immediately under a generic `mailchimp.com` URL form; the pretty `https://{dc}.campaign-archive.com/?u={audience-hash}&id={campaign_id}` form only appears once the campaign is scheduled in the Mailchimp UI (this tool never schedules, so getting the pretty URL is always a manual step). Confirmed by scheduling a real throwaway-turned-real campaign and observing the pretty URL become live without ever sending it.

## The surgical section re-patch pattern (not shipped here, described for reference)

A production version of this pipeline supported patching a small named subset of an existing draft's text regions (e.g. "just the third section changed") without rebuilding the whole campaign. The pattern, if you want to add it back:

1. `GET` the campaign first; refuse unless `status == 'save'` (once a campaign is scheduled, it can never return to a patchable draft state through any documented path — only to `paused`, and even then some UI-only actions like a manually-typed URL stub can't be reproduced via the API).
2. Read back the template's current `date_edited` and compare it against a baseline captured when the campaign was created. **`write_sections` re-renders the whole campaign from the template's *current* state before applying your named regions** — so any template edit made between campaign creation and a later patch can silently revert every template-driven region (most dangerously, images) to whatever the template now carries. Refuse the patch unless the baseline matches, with an explicit override for the confirmed-no-op case (remember: `date_edited` alone isn't proof of changed content).
3. Render every region, then write only the requested subset via the same `write_sections` call this tool already has.

This tool ships the delete-guard and the fixed rebuild-from-markdown recovery path instead (see AGENTS.md) — re-running `push.py` from the same markdown file after deleting a throwaway draft is cheap, and the image-reuse-by-size check means a re-run doesn't re-upload unchanged assets.

## Social card / Open Graph metadata (not shipped here)

`POST /campaigns` accepts a top-level `social_card` object (`title`, `description`, `image_url`) that controls the preview card shown when the campaign's public archive link is shared. This tool doesn't build or send one — it's out of scope for the demo — but the field exists if you want to add it back when adapting this pipeline.
