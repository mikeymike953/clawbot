# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Clawbot is a minimal Telegram bot implemented as a single-file Flask app (`app.py`). It receives updates via a Telegram webhook, and currently only echoes messages back (with a `ping` -> `pong` special case). It is deployed to Render as a web service.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (dev server)
python app.py
# Note: app.py has no `if __name__ == "__main__"` block or app.run() call,
# so running it directly will only execute set_webhook() at import time and exit.
# To actually serve requests locally, run it through gunicorn or flask instead:
flask --app app run
# or
gunicorn app:app
```

There are no tests, linter, or build step configured in this repository.

## Architecture

- `app.py` — the entire application:
  - `send_message(chat_id, text)` — POSTs a message to the Telegram Bot API (`sendMessage`).
  - `POST /telegram` — webhook endpoint Telegram calls with incoming updates. Parses `message.chat.id` and `message.text`, then replies via `send_message`.
  - `GET /health` — health check endpoint, returns `{"status": "healthy"}`.
  - `set_webhook()` — called at import time (module load). If both `RENDER_EXTERNAL_URL` and `TELEGRAM_BOT_TOKEN` env vars are set, it registers `{RENDER_EXTERNAL_URL}/telegram` as the bot's webhook URL with Telegram on every process start.
- `render.yaml` — Render deployment config: Python web service, `pip install -r requirements.txt` build, `gunicorn app:app` start command, `autoDeploy: true`.

### Configuration (environment variables)

- `TELEGRAM_BOT_TOKEN` — Telegram bot token, used to build `BASE_URL` (`https://api.telegram.org/bot{TOKEN}`) for all Telegram API calls.
- `RENDER_EXTERNAL_URL` — the public URL of the deployed Render service, used only by `set_webhook()` to tell Telegram where to send updates.

### Request flow

Telegram -> `POST /telegram` (on Render) -> `telegram_webhook()` reads `message.text` -> `send_message()` -> Telegram Bot API `sendMessage`.

Because `set_webhook()` runs at module import time (not gated behind `if __name__ == "__main__"`), every worker/process boot (including each gunicorn worker) re-registers the webhook if the env vars are present.
