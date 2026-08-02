# AGENTS.md — read this before touching any code in this directory

You are working on a tool that creates **draft** email campaigns in a real Mailchimp account via the Marketing API. The rules below are not suggestions — they are the safety contract this tool exists to enforce, and every one of them has a reason rooted in something that actually went wrong during development. Read `API-NOTES.md` for the underlying facts; this file is the imperative version.

## Never call send, test, resume, or schedule

Never construct a request to `/campaigns/{id}/actions/send`, `/actions/test`, `/actions/resume`, or `/actions/schedule`, in code, in a one-off script, or "just to verify the guard works." The client (`mailchimp_client.py`) hard-blocks any request path matching those actions before any HTTP call happens — do not weaken, narrow, or work around `_FORBIDDEN_PATTERN`. This tool creates drafts and stops there. The human reviews the draft in Mailchimp and sends and schedules it themselves, by hand, in the Mailchimp UI. Nothing in this codebase should ever move toward closing that gap.

## Never put an `html` key in a content write

`PUT /campaigns/{id}/content` with a top-level `html` key returns HTTP 200 and **silently wipes the campaign body** back to the base template's defaults. The only safe write is the sections form that `mailchimp_campaign.write_sections` already builds. If you're adding a new code path that writes campaign content, it must go through `write_sections` or build the exact same `{'template': {'id': ..., 'sections': {...}}}` shape — never a bare `html` key, ever.

## Never trust a 200 — keep the verify step

Region content cannot be read back from `GET /campaigns/{id}/content` (it carries no `template` key). The only way to know a write actually landed is to re-fetch the campaign's rendered `html` and check your content is actually in it — that's what `verify_rendered_html` does, and `push.py` calls it unconditionally at the end of every run. Do not add a code path that writes campaign content and skips this check.

## The write order is fixed: upload → patch template → create campaign → write sections

Image regions carry `mc:edit` directly on the `<img>` tag, which is the only way to get a real, hand-editable Image content block — and it's also what makes image regions **invisible to the API once a campaign exists**. There is no API call that can fix an existing draft's images. That's why images are uploaded and patched into a **copy of the template** before the campaign is ever created, never after. Do not reorder `push.py`'s `run()` to write sections before the campaign exists, or to patch images after campaign creation — both are unfixable mistakes, not just suboptimal ones.

## A sections payload containing `mc:edit` anywhere is silently discarded

If any region's value in a `template.sections` write contains the string `mc:edit`, the **entire write for that call** is a no-op — HTTP 200, nothing changes, no error. `newsletter_renderer.py` never emits `mc:edit` in rendered region content; keep it that way if you extend the renderer.

## Body text regions: one styled `<div>`, no `<p>`, no `<span>`, no styled links

The classic builder's editor pane renders these as **blank** if the markup doesn't match this shape exactly (see API-NOTES.md for the full rendering-rules table). This applies to **body regions** (`intro_text`, `section_N_text`, `reflect_text`) — **heading regions** (`intro_title`, `section_N_title`, `reflect_title`) are a different, equally-real shape: the region sits on the heading element itself (`mc:edit` is on the `<h2>` in `template.html`, not a wrapping `<div>`), so the payload is nested `<span>`s only, never a wrapping `<h2>` — writing a full `<h2>...</h2>` here nests a second `<h2>` inside the template's own one. `render_heading_spans` is the one function every heading region uses. Don't "fix" a heading region by stripping its spans, and don't add spans to a body region. All region HTML should come from `newsletter_renderer.py`'s existing rendering functions — don't add a second code path that hand-builds region markup differently.

## Only delete a campaign whose title contains 🔍, never one at status `schedule`

`delete_campaign_if_throwaway` is the only function in this codebase allowed to call `DELETE /campaigns/{id}`, and it refuses unless the campaign's title contains the 🔍 marker and its status is not `schedule`. Never add a second delete path, and never delete a campaign that wasn't created by this tool's own throwaway run.

## The human schedules in the Mailchimp UI — nothing here schedules, ever

This is the same rule as the first one, stated again because it's the point of the whole tool: this pipeline's job ends at a reviewable draft. Scheduling, sending, and any production-URL assignment happen in the Mailchimp web UI, by a human, after they've read the draft. Do not add a `--confirm-schedule`-style flag, a scheduling helper, or anything that reads or writes a campaign's `send_time` with intent to act on it.
