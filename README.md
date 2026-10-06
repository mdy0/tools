# tools

A collection of reusable scripts and utilities that serve as reference implementations for common tasks across projects. Each tool is self-contained in its own directory with its own README, credential templates, and setup instructions.

Inspired by [simonw/tools](https://github.com/simonw/tools).

## Tools

| Tool | What it does |
|------|-------------|
| [inoreader-read-api](inoreader-read-api/) | Fetch articles from Inoreader folders as JSON via OAuth 2.0 — auth setup, token refresh, paginated fetch, article normalization |
| [mailchimp-pipeline](mailchimp-pipeline/) | Two-stage newsletter pipeline — collect a markdown source-of-truth from a Google Sheet, push a draft Mailchimp campaign via the classic-builder API, with hard safety blocks against send/schedule |
| [markdown-copy-wp](markdown-copy-wp/) | `<markdown-copy>` web component for WordPress — renders markdown inline with a copy/toggle badge; no build step |
| [tg-send](tg-send/) | Send one-way messages to Telegram via the Bot API — no MCP, no framework dependency |
| [xteink-x3-http-api](xteink-x3-http-api/) | Unofficial HTTP API reference for the Xteink X3 eReader's Wi-Fi transfer server — endpoints, quirks, timeouts, examples; reference only, no code |

## Philosophy

Each tool here solved a real problem in a real project. The goal is not a polished library but a working reference: read the README, follow the setup steps, copy or adapt the code, and go.

Tools are designed to be dropped into a project as-is or installed at the user level and shared across projects.
