# tg-send

A minimal shell script for sending messages to Telegram from any script or automated workflow — and optionally editing them in place. Uses the Telegram Bot API directly via `curl` — no MCP server, no SDK, no framework dependency.

**What it does**: sends messages and, with the `--slot` flag, edits a previously sent message instead of posting a new one. This is useful for status updates that should show the current state rather than a growing thread of old states. It does not listen for replies.

**What it is not**: a chatbot framework or a two-way integration. For interactive bots or command routing, look elsewhere.

---

## One-time human setup

These steps require a human with a Telegram account. They only need to be done once per bot.

### 1. Create a bot via BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a username ending in `bot`).
3. BotFather will give you a **bot token** — a string like `123456789:ABCdef...`. Save it; this is your `TELEGRAM_BOT_TOKEN`.

### 2. Find the chat ID you want to send to

The chat ID tells the bot where to deliver messages. It can be a personal DM, a group, or a channel.

**For a personal DM (most common):**

1. Send your new bot any message (e.g., "hello") in Telegram.
2. Run `./get-chat-id.sh` — it will print the chat ID for every chat the bot has seen.
3. The ID for a personal DM is a positive integer (e.g., `123456789`).

**For a group:**

1. Add the bot to the group as a member.
2. Send any message in the group.
3. Run `./get-chat-id.sh` — the group will appear with `type=group` or `type=supergroup` and a negative ID (e.g., `-1001234567890`).

**For a channel:**

1. Add the bot as an **administrator** of the channel (it needs post permission).
2. Post anything to the channel.
3. Run `./get-chat-id.sh` — the channel will appear with `type=channel`.

**For a topic inside a forum-style supergroup:**

Topics are threads in supergroups that have the Topics feature enabled. Each topic has its own `message_thread_id`.

1. Make sure the bot is a member of the supergroup (you already have the group's chat ID).
2. Send `/start` **inside the topic** you want to target. Using a bot command rather than a plain message ensures the bot receives it even if privacy mode is enabled on the group.
3. Run `./get-chat-id.sh` — topic lines appear indented below their group, e.g.:
   ```
   chat_id=-1001234567890  type=supergroup  name=My Group
     topic  chat_id=-1001234567890  message_thread_id=42  name=Deployments
   ```
4. Use the `message_thread_id` with the `--topic` flag when sending.

### 3. Set up credentials

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and fill in both values:

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
CHAT_ID=123456789
```

`.env` is gitignored and must never be committed.

### 4. Make the scripts executable

```bash
chmod +x tg-send get-chat-id.sh
```

### 5. Test it

```bash
./tg-send "Hello from tg-send"
```

You should receive the message in Telegram within a second or two.

---

## Security

The bot token is the only credential this tool uses. Protecting it has three layers.

**File permissions**: `.env` should be `chmod 600` (owner read/write only) so other users on a shared machine cannot read it. `tg-send` sets the same permissions on `.message_ids.json` when it creates that file.

**Not committed**: `.env` and `.message_ids.json` are both gitignored at the tool level, and the repo root `.gitignore` is a backstop for `.env`.

**Not in the process list**: the bot token appears in the Telegram API URL. Rather than passing it as a command-line argument (where `ps aux` would expose it to every user on the machine), both scripts feed the URL to `curl` via stdin using the `-K -` flag. In normal sends, only the chat ID and message content appear in `curl`'s argv.

**Safe `.env` parsing**: both scripts use a Python stdlib parser rather than bash `source` to load the `.env` file. This means other keys in the same file (e.g. `WP_APP_PASSWORD=my password with spaces`) are ignored safely, making `TG_SEND_ENV` reliable when pointing at a project `.env` that contains values with spaces.

**What `.message_ids.json` contains**: when `--slot` is used, the script records `{ "CHAT_ID:slot-name": message_id }`. This is metadata, not a credential — but it does reveal which chats you're sending to, so it deserves the same gitignore treatment as `.env`.

**Slot names**: the slot key is stored in plain text in `.message_ids.json`. Do not embed sensitive information in slot names.

---

## Deployment options

### User-level (shared across projects)

Install once and use from any project on your machine:

```bash
mkdir -p ~/.local/bin
cp tg-send ~/.local/bin/tg-send
chmod +x ~/.local/bin/tg-send

mkdir -p ~/.config/tg-send
cp .env.example ~/.config/tg-send/.env
chmod 600 ~/.config/tg-send/.env
# edit ~/.config/tg-send/.env with your credentials

export TG_SEND_ENV=~/.config/tg-send/.env
# add that export to your shell profile (.zshrc / .bashrc)
```

Then call `tg-send "message"` from anywhere. When `--slot` is used, `.message_ids.json` is created in the same directory as `.env` (i.e., `~/.config/tg-send/`).

**Use this when**: you want one personal bot that handles alerts and messages across all your projects.

### Project-level (self-contained)

Copy the whole `tg-send/` directory into your project (e.g., `scripts/tg-send/`), add `.env` to your project's `.gitignore`, and call the script relative to the project root.

**Use this when**: the project has its own team, its own Telegram group, or you want the script versioned alongside the code that calls it.

---

## Usage

```bash
# Pass message as argument
./tg-send "Build finished successfully"

# Pipe from another command
echo "Deployment complete" | ./tg-send

# Pipe multi-line output
git log --oneline -5 | ./tg-send

# Send with HTML formatting
./tg-send --html "<b>Build failed</b> — see <code>build.log</code> for details"

# Send to a specific topic in a forum supergroup
./tg-send --topic 42 "Deploy finished"

# Topic + HTML
./tg-send --topic 42 --html "<b>Deploy finished</b> ✅"
```

### Updating a message in place

Pass `--slot KEY` to edit a previous message instead of sending a new one. The slot name is any string you choose — it identifies which message to update.

```bash
# First call: sends a new message and remembers it under "deploy-prod"
./tg-send --slot "deploy-prod" "Deploy started..."

# Later calls: edit the same message in Telegram
./tg-send --slot "deploy-prod" "Deploy complete ✅"
./tg-send --slot "deploy-prod" "Deploy rolled back ⚠️"

# With HTML formatting
./tg-send --slot "deploy-prod" --html "<b>Deploy complete</b> ✅"

# Scoped to a topic — slot tracks independently per topic
./tg-send --slot "deploy-prod" --topic 42 "Deploy started..."
./tg-send --slot "deploy-prod" --topic 42 "Deploy complete ✅"
```

When editing, `tg-send` appends `Last updated H:MM AM/PM` to the message so the reader knows it changed. With `--html`, this suffix is italicised (`<i>Last updated ...</i>`); without it, it's plain text. If the original message was deleted or is more than 48 hours old (Telegram's edit limit), a new message is sent and becomes the new tracked message for that slot.

Each `CHAT_ID + slot name` pair tracks independently, so multiple workflows sending to the same chat can each have their own tracked message.

### Sending files or attachments

The script sends text only. To send a file (photo, document, audio), use the Bot API's `sendDocument` or `sendPhoto` endpoints directly with `curl`:

```bash
# Send a file as a document
curl -s -X POST -K - \
  -F chat_id="${CHAT_ID}" \
  -F document=@"/path/to/file.pdf" \
  -F caption="Here is your file" <<EOF
url = "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument"
EOF
```

---

## Integrating with Python

Call `tg-send` as a subprocess after your main logic runs:

```python
import subprocess
from pathlib import Path

TG_SEND = Path(__file__).parent / "tg-send" / "tg-send"

def send_telegram(message: str, slot: str | None = None, html: bool = False, topic: int | None = None) -> None:
    cmd = [str(TG_SEND)]
    if slot:
        cmd += ["--slot", slot]
    if html:
        cmd.append("--html")
    if topic is not None:
        cmd += ["--topic", str(topic)]
    cmd.append(message)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Telegram send failed: {result.stderr}", file=sys.stderr)

# Send a one-off notification
send_telegram("Step 5 complete: 3 posts published")

# Send with HTML formatting
send_telegram("<b>Error:</b> pipeline failed at step 3", html=True)

# Send to a specific topic
send_telegram("Deploy finished", topic=42)

# Update a status message in place across multiple calls
send_telegram("Build started...", slot="build-main")
# ... later ...
send_telegram("<b>Build complete</b> ✅", slot="build-main", html=True)

# Slot scoped to a topic
send_telegram("Deploy started...", slot="deploy", topic=42)
# ... later ...
send_telegram("Deploy complete ✅", slot="deploy", topic=42)
```

If `tg-send` is on `PATH` (user-level install), omit the `TG_SEND` path and use `"tg-send"` directly.

---

## For Claude Code

This section describes how to set up `tg-send` in a new project context. Read the sections above first for background; this section is a checklist of actions.

### Prerequisites (human must do these first)

Before Claude Code can proceed, the human must complete:

1. **Create a Telegram bot** via @BotFather and have the bot token ready.
2. **Identify the target chat** (personal DM, group, or channel) and have the chat ID ready. If the chat ID is not known, run `get-chat-id.sh` after sending the bot a message.

Claude Code cannot retrieve credentials or perform Telegram account actions.

### Setup steps

**Step 1 — Copy the tool into the project** (or confirm user-level install exists):

For project-level: copy the `tg-send/` directory from this repo into the project (e.g., as `scripts/tg-send/`). Make scripts executable:

```bash
chmod +x scripts/tg-send/tg-send scripts/tg-send/get-chat-id.sh
```

For user-level: confirm `tg-send` is on PATH and `TG_SEND_ENV` points to a populated `.env`. The script defaults to a `.env` file in the same directory as the script itself — `TG_SEND_ENV` overrides that default, which is what allows one installed copy of the script to serve multiple projects, each with different credentials or a different target chat.

**Step 2 — Create the `.env` file** from the example:

```bash
cp scripts/tg-send/.env.example scripts/tg-send/.env
chmod 600 scripts/tg-send/.env
```

Then ask the human to fill in `TELEGRAM_BOT_TOKEN` and `CHAT_ID`.

**Step 3 — Add secrets to `.gitignore`**:

Check the project's `.gitignore` and add entries if not already present:

```
scripts/tg-send/.env
scripts/tg-send/.message_ids.json
```

**Step 4 — Test the connection**:

```bash
scripts/tg-send/tg-send "Test from [project name]"
```

Confirm the human receives the message before integrating further.

**Step 5 — Integrate into the relevant script**:

For Python, add a `send_telegram()` helper (see the Python integration section above) and call it at the appropriate point in the workflow. For shell scripts, call `tg-send` directly. Use `--slot` when you want repeated runs to update the same Telegram message rather than posting new ones.

### What to watch out for

- **Never write credentials into source files.** All tokens and chat IDs go in `.env`, which must be gitignored.
- **Gitignore `.message_ids.json` too.** It records which chats you're sending to. Treat it like `.env`.
- **Set file permissions.** Both `.env` and `.message_ids.json` should be `chmod 600`. The script sets permissions on `.message_ids.json` when it first creates the file; `.env` must be set manually.
- **Test before integrating.** A misconfigured bot token returns a 401 from the API; a wrong chat ID sends silently to nowhere. Always confirm receipt.
- **Channel bots need admin rights.** If sending to a channel, the bot must be an administrator with post permission — otherwise the API returns 400.
- **Chat IDs for groups are negative integers.** This is expected; do not treat it as an error.
- **Slot names are stored in plain text.** Do not put passwords, tokens, or other secrets in a slot name.
- **The 48-hour edit window.** Telegram does not allow editing messages older than 48 hours. `tg-send` handles this gracefully (falls back to a new message), but long-running workflows that span days will always send new messages rather than edit old ones.
- **`--html` and angle brackets.** Without `--html`, messages are plain text and `<` / `>` are safe to use literally. With `--html`, Telegram interprets the message as HTML — literal `<` and `>` must be escaped as `&lt;` and `&gt;` or they will be consumed silently, potentially mangling the message.
- **Topics require a forum-style supergroup.** The `--topic` flag only works in supergroups with the Topics feature enabled. Using it with a regular group, DM, or channel will return a 400 error from the API.
- **Privacy mode blocks plain messages when finding a topic ID.** If the group has privacy mode enabled, the bot won't see regular messages — send `/start` inside the topic instead. Bots always receive commands regardless of privacy mode.
- **Topic slots are independent.** A `--slot` used with `--topic 42` and the same `--slot` without `--topic` (or with a different topic) track separate messages. Same slot name, different scope.
- **`TG_SEND_ENV` is safe to point at any `.env` file.** The parser reads only `TELEGRAM_BOT_TOKEN` and `CHAT_ID`; all other keys are ignored, including ones with unquoted spaces that would break a bare `source`.
