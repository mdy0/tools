#!/usr/bin/env bash
# Print chat IDs from messages your bot has recently received.
#
# Run this after: (a) sending your bot a DM, or (b) adding it to a group
# and sending any message there. Telegram holds the last 100 updates.
#
# Usage: ./get-chat-id.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${TG_SEND_ENV:-$SCRIPT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: $ENV_FILE not found." >&2
  echo "At minimum, set TELEGRAM_BOT_TOKEN in your .env file." >&2
  exit 1
fi
source "$ENV_FILE"

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "Error: TELEGRAM_BOT_TOKEN not set in $ENV_FILE" >&2
  exit 1
fi

curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data.get('ok'):
    print('Error from Telegram API:', data.get('description', 'unknown'))
    sys.exit(1)
seen = {}
for update in data.get('result', []):
    chat = None
    if 'message' in update:
        chat = update['message'].get('chat', {})
    elif 'channel_post' in update:
        chat = update['channel_post'].get('chat', {})
    if chat and chat.get('id') not in seen:
        seen[chat['id']] = chat
if not seen:
    print('No chats found.')
    print('Send your bot a message (DM or group), then run this script again.')
    sys.exit(0)
for chat in seen.values():
    name = chat.get('title') or chat.get('username') or chat.get('first_name', 'unknown')
    print(f\"chat_id={chat['id']}  type={chat.get('type','?')}  name={name}\")
"
