# markdown-copy-wp

A `<markdown-copy>` custom element tailored for WordPress, adapted from Simon Willison's original. It renders markdown inline on a page with a floating badge. Clicking the badge opens a dropdown with two actions: **Copy** (copies raw markdown to clipboard) and **See code** (toggles between rendered HTML and raw markdown views).

No build step, no npm install. A single `<script type="module">` block is all that's needed — add it to your site's `<head>` via a code injection plugin (e.g. WPCode), a child theme's `functions.php`, or any other method that lets you output arbitrary HTML into the page header.

**What it is not**: a full markdown editor or a server-side renderer. Everything runs in the browser at render time.

**Security scope**: markdown content is injected into the Shadow DOM via `innerHTML` after being parsed by `marked`. This is safe when content comes from trusted authors (e.g. WordPress post editors) but is an XSS risk if untrusted users can supply markdown. This component is designed for the trusted-author case only. If you need to render user-submitted markdown, sanitize the output with [DOMPurify](https://github.com/cure53/DOMPurify) before insertion.

---

## Origin and Attribution

Adapted almost directly from Simon Willison's [`markdown-copy-component.html`](https://github.com/simonw/tools/blob/main/markdown-copy-component.html). The visual design, Shadow DOM structure, dropdown UI, all CSS, the `_dedent()` helper, the `_escapeHtml()` helper, and the event wiring are his work.

**WordPress-specific additions in this version:**

- `<script type="text/markdown">` as the preferred content source — avoids WordPress's `wptexturize` filter mangling backticks inside `<textarea>` content
- `<pre class="markdown-fallback">` removal on load — an email-client fallback that browsers never see (see WordPress integration section)
- Brand colors replacing Simon's original violet

---

## Dependencies

| Dependency | How used | Version tested |
|---|---|---|
| [`marked`](https://github.com/markedjs/marked) | Markdown → HTML rendering | 15.0.7 |
| Shadow DOM | Style encapsulation | Native browser API |
| Clipboard API | Copy to clipboard | Native browser API |

Loaded from cdnjs — no local install required:

```js
import { marked } from 'https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.7/lib/marked.esm.js';
```

**CDN tradeoff**: loading `marked` from cdnjs means every page visit sends a request to Cloudflare's CDN. This exposes visitor requests to a third party and creates a dependency on external availability. It will also fail if your site's Content Security Policy doesn't allowlist `cdnjs.cloudflare.com`. To avoid this, download `marked.esm.js` and self-host it, then update the import URL in the component.

---

## One-time human setup

None. This is a browser-only component with no server-side dependencies, no API keys, and no accounts required.

---

## Deployment options

### Inline script block (recommended for WordPress)

Wrap the contents of `markdown-copy-wp-component.js` in a `<script type="module">` tag and add it to your site's `<head>` via whichever method your setup supports — a code injection plugin (e.g. WPCode's Header & Footer field), a child theme's `functions.php`, or similar.

```html
<script type="module">
/* paste contents of markdown-copy-wp-component.js here */
</script>
```

**Use this when**: you're on WordPress and don't want to serve arbitrary static files.

### Hosted script file

Serve `markdown-copy-wp-component.js` as a static file and reference it:

```html
<script type="module" src="/path/to/markdown-copy-wp-component.js"></script>
```

**Use this when**: you control your server and want to update the component in one place across many pages.

---

## Usage

Include the script once, then use `<markdown-copy>` wherever you want:

```html
<markdown-copy>
  <script type="text/markdown">
## Your Heading

Content here. **Bold**, *italic*, `code`, [links](https://example.com).

- Lists work
- Tables work
- Fenced code blocks work
  </script>
</markdown-copy>
```

### Content source options (in priority order)

1. `<script type="text/markdown">` — preferred; browser ignores it, no CMS filter mangles it
2. `<textarea>` — Simon's original approach; fine for plain HTML, problematic in some CMS environments
3. Plain text content — last fallback; not recommended, some parsers will process it

---

## WordPress integration

### Why `<script type="text/markdown">`

WordPress's `wptexturize` filter converts straight backticks inside `<textarea>` values to typographic quotes, breaking code blocks. `<script type="text/markdown">` avoids this — browsers ignore it and `wptexturize` does not process it.

### Using in WordPress posts

In the Gutenberg editor, add a **Custom HTML** block wherever you want the component to appear. Paste the `<markdown-copy>` tag into it:

```html
<markdown-copy>
  <script type="text/markdown">
## Your Heading

Your markdown content here.
  </script>
</markdown-copy>
```

Each post can have as many Custom HTML blocks (and therefore as many `<markdown-copy>` instances) as needed. The component script registered in the page header handles all of them automatically.

### Email newsletter fallback (Mailchimp)

Mailchimp strips `<script>` tags. Add a `<pre class="markdown-fallback">` alongside the script tag — it renders as plain text in email and is silently removed by the component in browsers:

```html
<markdown-copy>
  <script type="text/markdown">
Your markdown here
  </script>
  <pre class="markdown-fallback" style="white-space: pre-wrap; font-family: monospace; font-size: 0.9em; background: #f9fafb; padding: 1em; border-radius: 6px;">
Your markdown here (plain text fallback for email)
  </pre>
</markdown-copy>
```

`<pre>` is safe from `wptexturize` — WordPress skips its contents.

---

## Customization

| Thing to change | Where in the JS |
|---|---|
| Badge background / text / border color | `.tag` — `background`, `color`, `border` (3 values) |
| Badge hover color | `.tag:hover` — `background` (1 value) |
| Blockquote accent | `.rendered blockquote` — `border-left` color and `background` |
| `marked` version | The CDN import URL at the top of the file |
| Badge label text | `'markdown'` string in the `<button class="tag">` in `shadowRoot.innerHTML` |

**Current colors** (brand red):

| Element | Property | Value |
|---|---|---|
| `.tag` | background | `#fbeaea` |
| `.tag` | color | `#b41d1d` |
| `.tag` | border | `#f0bebe` |
| `.tag:hover` | background | `#f5d0d0` |
| `.rendered blockquote` | border-left color | `#f0bebe` |
| `.rendered blockquote` | background | `#fdf5f5` |

Simon's original violet values: `#eef0ff` / `#5b5fc7` / `#d4d7ff` (hover: `#dde0ff`), blockquote: `#c5a3ff` / `#faf7ff`.

---

## For AI coding agents

### Prerequisites

None — no credentials, no accounts, no human action required before an AI coding agent can proceed.

### Setup steps

**Step 1 — Register the component site-wide:**

An AI coding agent cannot inject code into WordPress directly. Read the contents of `markdown-copy-wp-component.js`, wrap it in a `<script type="module">` tag, and give the user the following block to add to their site's `<head>` via their preferred method (WPCode, `functions.php`, or similar):

```html
<script type="module">
/* contents of markdown-copy-wp-component.js */
</script>
```

The component is now available on every page of the site. This step is done once.

**Step 2 — Add the component to a post or page:**

In the Gutenberg editor, insert a **Custom HTML** block and paste a `<markdown-copy>` tag into it:

```html
<markdown-copy>
  <script type="text/markdown">
## Heading

Your markdown content here.
  </script>
</markdown-copy>
```

Repeat for each block of markdown content in the post. Multiple instances on one page work independently.

### What to watch out for

- **The HTML tag is `<markdown-copy>`, not `<markdown-copy-wp>`** — the file is named `markdown-copy-wp-component.js` but the registered custom element is `<markdown-copy>`. That is what you write in the Custom HTML block.
- **Double-injection guard is intentional** — `customElements.define` throws if called twice for the same tag. The `if (!customElements.get('markdown-copy'))` guard prevents this in WordPress, where a plugin, theme, and WPCode can each independently inject the same header script.
- **`<script type="text/markdown">` not `<script>`** — the `type` attribute is what prevents the browser from executing the content. Omitting it will cause the browser to try to execute the markdown as JavaScript.
- **WordPress textarea mangling** — if content appears with curly quotes instead of straight backticks, `wptexturize` got to a `<textarea>`. Switch to `<script type="text/markdown">`.
- **Mailchimp strips `<script>` tags** — if the component is used in posts that go to email subscribers, always include a `<pre class="markdown-fallback">` alongside the script tag.
- **`marked` version pinned to CDN URL** — if upgrading `marked`, update the import URL and test; the API has changed across major versions.
- **CSP may block the cdnjs import** — if the site has a `Content-Security-Policy` header that doesn't allowlist `cdnjs.cloudflare.com`, the import will fail silently and no markdown will render. Either add the CDN to the allowlist or self-host `marked.esm.js`.
- **XSS risk with untrusted content** — `marked.parse()` output is injected directly into `innerHTML`. This component is designed for trusted authors only (WordPress post editors). Do not use it to render user-submitted markdown without sanitizing first — see [DOMPurify](https://github.com/cure53/DOMPurify).
- **Shadow DOM means external CSS won't reach inside** — styles applied to `markdown-copy` from a parent stylesheet do not penetrate the shadow root. All component styling lives inside the `static get styles()` block.
- **Clipboard API requires HTTPS** — `navigator.clipboard.writeText()` is blocked on plain HTTP origins in most browsers. The Copy button will silently fail on `http://` pages.
