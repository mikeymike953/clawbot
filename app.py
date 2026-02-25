import os
import threading
import time
from flask import Flask, jsonify

app = Flask(__name__)

def clawbot_loop():
    # This is your bot loop. We'll plug in your real logic later.
    while True:
        try:
            print("Clawbot tick...")
            time.sleep(30)
        except Exception as e:
            print("Clawbot error:", repr(e))
            time.sleep(10)

@app.get("/")
def home():
    return jsonify(status="ok", service="clawbot")

@app.get("/health")
def health():
    return jsonify(status="healthy")

def start_bot():
    t = threading.Thread(target=clawbot_loop, daemon=True)
    t.start()

# Gunicorn imports "app" from this file, so we start the bot on import.
start_bot()
