import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# ---- Helper: Send message ----
def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

# ---- Telegram Webhook Endpoint ----
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Basic assistant logic
        if text.lower() == "ping":
            send_message(chat_id, "pong")
        else:
            send_message(chat_id, f"You said: {text}")

    return jsonify(success=True)

@app.route("/health")
def health():
    return jsonify(status="healthy")

# ---- Auto-register webhook on startup ----
# ---- Auto-register webhook on startup ----
def set_webhook():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url and TOKEN:
        webhook_url = f"{render_url}/telegram"
        requests.get(f"{BASE_URL}/setWebhook", params={"url": webhook_url})

set_webhook()
