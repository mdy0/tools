# tg-send

A minimal shell script for sending one-way messages to Telegram from any script or automated workflow. Uses the Telegram Bot API directly via `curl` — no MCP server, no SDK, no framework dependency.

**What "one-way" means**: this tool sends messages; it does not listen for replies. It's the right fit for notifications, status updates, log tails, file delivery, or any situation where a script needs to reach a human through Telegram.

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

### 3. Set up credentials

```bash
cp .env.example .env
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

## Deployment options

### User-level (shared across projects)

Install once and use from any project on your machine:

```bash
mkdir -p ~/.local/bin
cp tg-send ~/.local/bin/tg-send
chmod +x ~/.local/bin/tg-send

mkdir -p ~/.config/tg-send
cp .env.example ~/.config/tg-send/.env
# edit ~/.config/tg-send/.env with your credentials

export TG_SEND_ENV=~/.config/tg-send/.env
# add that export to your shell profile (.zshrc / .bashrc)
```

Then call `tg-send "message"` from anywhere.

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

# From anywhere if installed user-level
tg-send "Hello"
```

### Sending files or attachments

The script sends text only. To send a file (photo, document, audio), use the Bot API's `sendDocument` or `sendPhoto` endpoints directly with `curl`:

```bash
# Send a file as a document
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
  -F chat_id="${CHAT_ID}" \
  -F document=@"/path/to/file.pdf" \
  -F caption="Here is your file"
```

A future version of this tool may wrap this as a `tg-send --file` flag.

---

## Integrating with Python

Call `tg-send` as a subprocess after your main logic runs:

```python
import subprocess

def send_telegram(message: str) -> None:
    result = subprocess.run(
        ["tg-send", message],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Telegram send failed: {result.stderr}", file=sys.stderr)

# Example: send status at end of a script
send_telegram("Step 5 complete: 3 posts published, blurbs done, email ready")
```

If `tg-send` is not on `PATH` (project-level install), use the full path:

```python
TG_SEND = Path(__file__).parent / "tg-send" / "tg-send"
subprocess.run([str(TG_SEND), message])
```

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
```
Then ask the human to fill in `TELEGRAM_BOT_TOKEN` and `CHAT_ID`.

**Step 3 — Add `.env` to `.gitignore`**:

Check the project's `.gitignore` and add an entry if not already present:
```
scripts/tg-send/.env
```

**Step 4 — Test the connection**:
```bash
scripts/tg-send/tg-send "Test from [project name]"
```
Confirm the human receives the message before integrating further.

**Step 5 — Integrate into the relevant script**:

For Python, add a `send_telegram()` helper (see the Python integration section above) and call it at the appropriate point in the workflow. For shell scripts, call `tg-send` directly.

### What to watch out for

- **Never write credentials into source files.** All tokens and chat IDs go in `.env`, which must be gitignored.
- **Test before integrating.** A misconfigured bot token returns a 401 from the API; a wrong chat ID sends silently to nowhere. Always confirm receipt.
- **Channel bots need admin rights.** If sending to a channel, the bot must be an administrator with post permission — otherwise the API returns 400.
- **Chat IDs for groups are negative integers.** This is expected; do not treat it as an error.
