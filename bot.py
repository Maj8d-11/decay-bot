import os
import re
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
import requests

# ==========================================================
# DECAY DISCORD BOT v3 FIXED
# Supports:
# - /nearest
# - /test
# - auto alerts via BOT channel ID, not only webhook
# - optional webhook fallback
# Base file time:
# May 4, 2026 - 6:13 PM Jordan time
# ==========================================================

BASE_TIME = datetime(2026, 5, 4, 18, 13, 0, tzinfo=ZoneInfo("Asia/Amman"))

TXT_FILE = os.getenv("TXT_FILE", "decay.txt")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Recommended: bot sends auto alerts to this channel.
# Discord channel ID, example: 123456789012345678
ALERT_CHANNEL_ID_RAW = os.getenv("ALERT_CHANNEL_ID", "").strip()
ALERT_CHANNEL_ID = int(ALERT_CHANNEL_ID_RAW) if ALERT_CHANNEL_ID_RAW.isdigit() else None

# Optional fallback/old method
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

ALERT_MINUTES = int(os.getenv("ALERT_MINUTES", "10"))
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "60"))
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
    if not os.path.exists(TXT_FILE):
        print(f"[ERROR] TXT file not found: {TXT_FILE}")
        return []

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


def get_upcoming_worlds(limit=5):
    now = datetime.now(ZoneInfo("Asia/Amman"))
    upcoming = []

    for world, decay_time in parse_worlds():
        seconds_left = int((decay_time - now).total_seconds())
        if seconds_left >= 0:
            upcoming.append((world, decay_time, seconds_left))

    upcoming.sort(key=lambda item: item[2])
    return upcoming[:limit]


def make_decay_embed(world: str, decay_time: datetime, seconds_left: int, title="🌍 World Decay Alert"):
    embed = discord.Embed(
        title=title,
        description=f"**`{world}`** is about to decay.",
        color=0xFF0000
    )
    embed.add_field(name="World", value=f"`{world}`", inline=True)
    embed.add_field(name="Time Left", value=f"**{format_left(seconds_left)}**", inline=True)
    embed.add_field(
        name="Decay Time",
        value=decay_time.strftime("%Y-%m-%d %I:%M:%S %p Jordan time"),
        inline=False
    )
    embed.add_field(name="Alert Threshold", value=f"{ALERT_MINUTES} minutes before decay", inline=True)
    embed.set_footer(text="Decay Bot v3 • Based on 2026-05-04 6:13 PM Jordan time")
    return embed


def send_webhook_fallback(world: str, decay_time: datetime, seconds_left: int):
    if not DISCORD_WEBHOOK_URL:
        return False

    mention = "@everyone\n" if MENTION_EVERYONE else ""
    payload = {
        "content": f"{mention}🚨 **WORLD DECAY SOON: `{world}`**",
        "embeds": [
            {
                "title": "🌍 World Decay Alert",
                "description": f"**`{world}`** is about to decay.",
                "color": 16711680,
                "fields": [
                    {"name": "World", "value": f"`{world}`", "inline": True},
                    {"name": "Time Left", "value": f"**{format_left(seconds_left)}**", "inline": True},
                    {"name": "Decay Time", "value": decay_time.strftime("%Y-%m-%d %I:%M:%S %p Jordan time"), "inline": False},
                ],
                "footer": {"text": "Decay Bot v3 webhook fallback"}
            }
        ],
        "allowed_mentions": {"parse": ["everyone"]}
    }

    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    r.raise_for_status()
    return True


class DecayClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.bg_task = asyncio.create_task(auto_alert_loop())
        await self.tree.sync()
        print("[OK] Slash commands synced globally. It can take a few minutes to appear.")


client = DecayClient()


async def send_bot_alert(world: str, decay_time: datetime, seconds_left: int):
    if not ALERT_CHANNEL_ID:
        return False

    channel = client.get_channel(ALERT_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(ALERT_CHANNEL_ID)
        except Exception as e:
            print("[ERROR] Cannot fetch ALERT_CHANNEL_ID:", repr(e))
            return False

    mention = "@everyone\n" if MENTION_EVERYONE else ""
    embed = make_decay_embed(world, decay_time, seconds_left)

    try:
        await channel.send(content=f"{mention}🚨 **WORLD DECAY SOON: `{world}`**", embed=embed)
        return True
    except discord.Forbidden:
        print("[ERROR] Bot has no permission to send messages / mention everyone / embed links in alert channel.")
        return False
    except Exception as e:
        print("[ERROR] Bot alert failed:", repr(e))
        return False


async def auto_alert_loop():
    await client.wait_until_ready()
    alerted = load_alerted()

    while not client.is_closed():
        try:
            now = datetime.now(ZoneInfo("Asia/Amman"))

            for world, decay_time in parse_worlds():
                seconds_left = int((decay_time - now).total_seconds())

                if seconds_left < 0:
                    continue

                alert_key = f"{world}|{decay_time.isoformat()}"

                if alert_key in alerted:
                    continue

                if seconds_left <= ALERT_MINUTES * 60:
                    sent = await send_bot_alert(world, decay_time, seconds_left)

                    if not sent and DISCORD_WEBHOOK_URL:
                        try:
                            sent = send_webhook_fallback(world, decay_time, seconds_left)
                        except Exception as e:
                            print("[ERROR] Webhook fallback failed:", repr(e))
                            sent = False

                    if sent:
                        alerted.add(alert_key)
                        save_alerted(alerted)
                        print(f"[SENT] {world} | left: {format_left(seconds_left)} | decay: {decay_time}")
                    else:
                        print(f"[NOT SENT] {world} | configure ALERT_CHANNEL_ID or DISCORD_WEBHOOK_URL")

        except Exception as e:
            print("[AUTO ALERT ERROR]", repr(e))

        await asyncio.sleep(CHECK_EVERY_SECONDS)


@client.event
async def on_ready():
    print("======================================")
    print("Decay Bot v3 Fixed started")
    print("======================================")
    print(f"Logged in as: {client.user}")
    print(f"Base time: {BASE_TIME.isoformat()}")
    print(f"TXT file: {TXT_FILE}")
    print(f"Worlds loaded: {len(parse_worlds())}")
    print(f"Alert threshold: {ALERT_MINUTES} minutes")
    print(f"Alert channel ID: {ALERT_CHANNEL_ID if ALERT_CHANNEL_ID else 'Not set'}")
    print(f"Webhook fallback: {'ON' if DISCORD_WEBHOOK_URL else 'OFF'}")
    print(f"Mention everyone: {MENTION_EVERYONE}")
    print(f"Watchlist: {', '.join(sorted(WATCHLIST)) if WATCHLIST else 'All worlds'}")
    print("Commands: /nearest, /test")


@client.tree.command(name="nearest", description="Shows the nearest decaying worlds.")
@app_commands.describe(count="How many nearest worlds to show, from 1 to 20.")
async def nearest(interaction: discord.Interaction, count: int = 5):
    count = max(1, min(count, 20))
    upcoming = get_upcoming_worlds(limit=count)

    if not upcoming:
        await interaction.response.send_message("No upcoming worlds found.", ephemeral=True)
        return

    lines = []
    for index, (world, decay_time, seconds_left) in enumerate(upcoming, start=1):
        lines.append(
            f"**{index}. `{world}`**\n"
            f"⏳ Time left: **{format_left(seconds_left)}**\n"
            f"🕒 Decay: `{decay_time.strftime('%Y-%m-%d %I:%M:%S %p')} Jordan time`"
        )

    embed = discord.Embed(
        title="🌍 Nearest Decaying Worlds",
        description="\n\n".join(lines),
        color=0xFF9900
    )
    embed.set_footer(text="Decay Bot v3 • Based on 2026-05-04 6:13 PM Jordan time")

    await interaction.response.send_message(embed=embed)


@client.tree.command(name="test", description="Sends a test decay alert in this channel.")
async def test(interaction: discord.Interaction):
    now = datetime.now(ZoneInfo("Asia/Amman"))
    decay_time = now + timedelta(minutes=5)
    embed = make_decay_embed("TESTWORLD", decay_time, 5 * 60, title="🧪 Test Alert")

    mention = "@everyone\n" if MENTION_EVERYONE else ""

    try:
        await interaction.response.send_message(
            content=f"{mention}🧪 **TEST ALERT: `TESTWORLD`**",
            embed=embed
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I do not have permission to send messages or embeds here.",
            ephemeral=True
        )


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable.")

    client.run(DISCORD_BOT_TOKEN)
