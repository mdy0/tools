#!/usr/bin/env bash
# Print chat IDs (and topic IDs) from messages your bot has recently received.
#
# Run this after: (a) sending your bot a DM, (b) adding it to a group and
# sending any message there, or (c) sending a message in a group topic.
# Telegram holds the last 100 updates.
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
seen_chats = {}
seen_topics = {}
for update in data.get('result', []):
    msg = update.get('message') or update.get('channel_post')
    if not msg:
        continue
    chat = msg.get('chat', {})
    chat_id = chat.get('id')
    if chat_id and chat_id not in seen_chats:
        seen_chats[chat_id] = chat
    thread_id = msg.get('message_thread_id')
    if thread_id and chat_id:
        key = (chat_id, thread_id)
        if key not in seen_topics:
            seen_topics[key] = msg.get('reply_to_message', {}).get('forum_topic_created', {}).get('name', '(topic name unknown)')
if not seen_chats:
    print('No chats found.')
    print('Send your bot a message (DM or group), then run this script again.')
    sys.exit(0)
for chat in seen_chats.values():
    name = chat.get('title') or chat.get('username') or chat.get('first_name', 'unknown')
    print(f\"chat_id={chat['id']}  type={chat.get('type','?')}  name={name}\")
for (chat_id, thread_id), topic_name in seen_topics.items():
    print(f\"  topic  chat_id={chat_id}  message_thread_id={thread_id}  name={topic_name}\")
"
