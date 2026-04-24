# CLAUDE.md — tools repo

## What this repo is

A collection of reusable reference implementations for common tasks. Each tool is a working example extracted from a real project, generalized so it can be adapted to new contexts without re-deriving the solution from scratch.

The primary audience is a future session of Claude Code working on a different project that needs similar functionality. The secondary audience is a human who wants to understand what was built and why.

## Conventions

### One subdirectory per tool

Every tool lives in its own subdirectory named in kebab-case (e.g., `tg-send/`). A tool is never a single flat file at the repo root — it always has at least a script and a README.

### Required files in every tool directory

```
tool-name/
  README.md         # see structure below
  .env.example      # if the tool needs credentials — never the real .env
  .gitignore        # must ignore .env and any other secrets
```

Plus whatever scripts, helpers, or config the tool needs.

### README structure every tool must follow

1. **What it is** — one paragraph: what it does, what "one-way" or other key constraint means, what it is *not*
2. **One-time human setup** — numbered steps a human must do before any code runs (account creation, API keys, etc.)
3. **Deployment options** — at minimum: user-level (shared across projects) vs project-level (self-contained in repo), with tradeoffs and "use this when" guidance
4. **Usage** — copy-pasteable CLI examples covering the main cases
5. **Integration** — how to call the tool from another language (Python, shell, etc.)
6. **For Claude Code** — structured setup checklist (see below)

### The "For Claude Code" section

This is the most important section for reuse. It must include:

- **Prerequisites** — what the human must do before Claude Code can proceed (Claude Code cannot create accounts, retrieve credentials, or perform actions that require a logged-in human)
- **Setup steps** — numbered, actionable, with exact commands
- **What to watch out for** — non-obvious failure modes (silent failures, permission requirements, negative IDs, etc.)

### Credentials and secrets

- Every tool that needs credentials must have a `.env.example` with placeholder values
- Every tool directory must have a `.gitignore` that ignores `.env`
- The repo root `.gitignore` also ignores `.env` as a backstop
- **Never hardcode tokens, chat IDs, API keys, or any credentials in scripts** — they go in `.env` only

### Adding a new tool

1. Create `tool-name/` subdirectory
2. Write the script(s) — generalized, no hardcoded credentials or project-specific values
3. Write `README.md` following the structure above
4. Add `.env.example` and `.gitignore` if credentials are needed
5. Update the repo root `README.md` to add the tool to the catalog table
6. Commit and push

## Session logs

Session logs go in `session-logs/` at the repo root (gitignored). Follow the same naming convention as other projects: `YYYYMmmDD-descriptive-stub.md`.

## What not to put here

- Polished, production-ready libraries — this is a reference collection, not a package
- Tools that are too project-specific to generalize
- Any file containing real credentials
