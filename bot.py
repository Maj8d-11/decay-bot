import os
import re
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ==========================================================
# DECAY DISCORD ALERT BOT
# Base file time requested by user:
# May 4, 2026 - 6:13 PM Jordan time
# ==========================================================

BASE_TIME = datetime(2026, 5, 4, 18, 13, 0, tzinfo=ZoneInfo("Asia/Amman"))

TXT_FILE = os.getenv("TXT_FILE", "decay.txt")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Alert when world has <= this many minutes left
ALERT_MINUTES = int(os.getenv("ALERT_MINUTES", "10"))

# Check interval
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "60"))

# Mention everyone? default yes
MENTION_EVERYONE = os.getenv("MENTION_EVERYONE", "true").lower() in ("true", "1", "yes", "y")

# Optional: only alert selected worlds.
# Example:
# WATCHLIST=REPLY,SPECIAL,AMMAN
WATCHLIST_RAW = os.getenv("WATCHLIST", "").strip()
WATCHLIST = {w.strip().upper() for w in WATCHLIST_RAW.split(",") if w.strip()} if WATCHLIST_RAW else set()

ALERTED_FILE = "alerted.json"


def load_alerted():
    if not os.path.exists(ALERTED_FILE):
        return set()
    try:
        with open(ALERTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_alerted(alerted):
    with open(ALERTED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(alerted), f, indent=2)


def duration_to_seconds(text: str) -> int:
    days = hours = minutes = seconds = 0

    m = re.search(r"(\d+)\s+days?", text)
    if m:
        days = int(m.group(1))

    m = re.search(r"(\d+)\s+hours?", text)
    if m:
        hours = int(m.group(1))

    m = re.search(r"(\d+)\s+minutes?", text)
    if m:
        minutes = int(m.group(1))

    m = re.search(r"(\d+)\s+seconds?", text)
    if m:
        seconds = int(m.group(1))

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def format_left(seconds_left: int) -> str:
    seconds_left = max(0, int(seconds_left))
    d, rem = divmod(seconds_left, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def parse_worlds():
    worlds = []

    with open(TXT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "|" not in line:
                continue

            parts = line.split("|", 1)
            world = parts[0].strip().upper()
            timer_text = parts[1].strip()

            if not world or world.startswith("HTTP") or "Charon Client" not in timer_text:
                continue

            if WATCHLIST and world not in WATCHLIST:
                continue

            seconds_after_base = duration_to_seconds(timer_text)
            if seconds_after_base <= 0:
                continue

            decay_time = BASE_TIME + timedelta(seconds=seconds_after_base)
            worlds.append((world, decay_time))

    worlds.sort(key=lambda item: item[1])
    return worlds


def send_discord_alert(world: str, decay_time: datetime, seconds_left: int):
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL environment variable.")

    mention = "@everyone\n" if MENTION_EVERYONE else ""

    content = f"{mention}🚨 **WORLD DECAY SOON: `{world}`**"

    embed = {
        "title": "🌍 World Decay Alert",
        "description": f"**`{world}`** is about to decay.",
        "color": 16711680,
        "fields": [
            {
                "name": "World",
                "value": f"`{world}`",
                "inline": True
            },
            {
                "name": "Time Left",
                "value": f"**{format_left(seconds_left)}**",
                "inline": True
            },
            {
                "name": "Decay Time",
                "value": decay_time.strftime("%Y-%m-%d %I:%M:%S %p Jordan time"),
                "inline": False
            },
            {
                "name": "Alert Threshold",
                "value": f"{ALERT_MINUTES} minutes before decay",
                "inline": True
            },
            {
                "name": "Source Time",
                "value": "File based on 2026-05-04 06:13 PM Jordan time",
                "inline": False
            }
        ],
        "footer": {
            "text": "Decay Alert Bot"
        }
    }

    payload = {
        "content": content,
        "embeds": [embed],
        "allowed_mentions": {
            "parse": ["everyone"]
        }
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    r.raise_for_status()


def main():
    print("======================================")
    print("Decay Discord Alert Bot v2 started")
    print("======================================")
    print(f"Base time: {BASE_TIME.isoformat()}")
    print(f"TXT file: {TXT_FILE}")
    print(f"Alert threshold: {ALERT_MINUTES} minutes")
    print(f"Mention everyone: {MENTION_EVERYONE}")
    print(f"Watchlist: {', '.join(sorted(WATCHLIST)) if WATCHLIST else 'All worlds'}")
    print("Press CTRL+C to stop.")
    print("")

    alerted = load_alerted()

    while True:
        now = datetime.now(ZoneInfo("Asia/Amman"))

        try:
            worlds = parse_worlds()

            for world, decay_time in worlds:
                seconds_left = int((decay_time - now).total_seconds())

                if seconds_left < 0:
                    continue

                alert_key = f"{world}|{decay_time.isoformat()}"

                if alert_key in alerted:
                    continue

                if seconds_left <= ALERT_MINUTES * 60:
                    send_discord_alert(world, decay_time, seconds_left)
                    alerted.add(alert_key)
                    save_alerted(alerted)
                    print(f"[SENT] {world} | left: {format_left(seconds_left)} | decay: {decay_time}")

        except Exception as e:
            print("[ERROR]", repr(e))

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
