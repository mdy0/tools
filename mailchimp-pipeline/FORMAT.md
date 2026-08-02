# FORMAT.md — the newsletter markdown contract

This is the file `push.py` reads and `collect.py` writes. It is the contract between the two stages: anything that produces a file in this exact shape can feed Stage 2, and Stage 2 never needs to know where the file came from. Read this before writing a new collector — you should not need to read `collect.py`, `newsletter_markdown.py`, or `push.py` to write a conforming file by hand.

The shape is a header block of `**Field:** value` lines, followed by `##` sections. It is not YAML frontmatter — the header lines are plain markdown, parsed line-by-line, and the file stays easy to hand-edit and diff.

## Full shape

```markdown
# Newsletter

**Subject:** AI This Week — breaches, vanishing traffic, and the model ensemble
**Preview Text:** Three stories worth your attention this week
**Date:** 2026-08-02
**Banner:** images/banner.png
**Banner Alt:** AI This Week
**Banner Link:** https://example.com/archive

## Intro

### {intro heading — one line}

{one or more paragraphs, blank-line separated}

## This Week

### {section 1 headline}

**Source:** {attribution, e.g. "Malwarebytes Labs"}

{summary: one or two paragraphs, blank-line separated; may contain [label](url) inline links}

---

### {section 2 headline}
… (same block shape) …

---

### {section 3 headline}
… (same block shape) …

## Worth Reflecting

- {question}
- {question}
- {question}
```

## Field rules

### Header block

- `**Subject:**` — the campaign subject line. Required.
- `**Preview Text:**` — the inbox preview snippet. Required.
- `**Date:**` — `YYYY-MM-DD`. Required. `collect.py` uses it to name its output file when no `--out` path is given.
- `**Banner:**` — a path to the banner image, **relative to the markdown file's own directory** (not the current working directory, not the repo root). Required. The resolved path must stay within that directory — an absolute path or a `../` that walks outside it is refused (`AssetError`), not silently followed.
- `**Banner Alt:**` — alt text for the banner image. Required.
- `**Banner Link:**` — a URL the banner links to, or a literal `—` (em dash) to mean "the banner is not linked." Required (the em dash is a valid value, not an omission).

### `## Intro`

One `### {heading}` line (the hero heading, one line, no markdown formatting inside it) followed by one or more paragraphs, separated by a blank line. The section ends at the next `## ` heading — a malformed intro cannot swallow the sections that follow it.

### `## This Week`

Exactly **three** section blocks, each shaped:

```markdown
### {headline}

**Source:** {attribution}

{summary paragraph(s), blank-line separated}
```

separated from each other by a line containing only `---`.

- The **summary** may contain inline `[label](url)` links — those render as ordinary hyperlinks in the pushed campaign.
- The **summary** may also contain `**bold**` markdown — it converts to `<strong>`. This and the inline-link support above apply everywhere prose is rendered: the intro paragraphs and the Worth Reflecting questions get the same treatment, not just section summaries.
- One of the summary's blank-line-separated paragraphs may instead be a **bullet block**: every line in it starts with `- ` (no blank lines between the lines — that's what makes it one "paragraph" rather than several). It renders as `•`-marked lines inside the same styled block, not as ordinary prose. A paragraph that mixes bullet and non-bullet lines is treated as prose (its `- ` lines render literally) — keep a bullet block's lines uniform.
- The template has exactly three section slots. A collector that produces a different count is a contract violation — `newsletter_markdown.py` aborts and names the count it found (that check is what actually enforces the limit; `newsletter_renderer.py` is count-agnostic, it just loops over however many sections it's handed). Changing the section count means regenerating `template.html` via `make_template.py` (never hand-edit `template.html` itself — it's generated output, committed only so a clone works without running the generator) and updating that count check in `newsletter_markdown.py` too; it is not a Stage-1-only change.

### `## Worth Reflecting`

A `- ` bullet list, 1–5 items, one question per line. No sub-fields. The `- ` markers are markdown structure only, not a rendering instruction: each question becomes its own paragraph, and the pushed campaign shows them as separate paragraphs (`<br><br>`-joined), not as a bulleted list. This is different from a **bullet block** inside a section summary (above), where the `- ` markers *do* render as `•`-marked lines — the distinction is that a Worth Reflecting question is always its own list item (and so its own paragraph after parsing), while a bullet block is multiple `- ` lines inside one summary paragraph.

## Why this file exists

The markdown file is the reviewable, re-runnable source of truth for a send: a human reads it before anything touches the network, and a failed or partial push can be re-run from the same file with no state lost. Hand-edits to this file are what actually get pushed — `push.py` never writes back into it.
