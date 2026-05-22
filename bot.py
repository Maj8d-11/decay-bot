import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
import requests

# ==========================================================
# DECAY DISCORD BOT v4
# Features:
# - Real UTC timestamp support
# - Jordan timezone conversion
# - Ignores already decayed worlds
# - Reads only UPCOMING DECAYS section
# - /nearest command
# - /test command
# - Auto alerts
# - Optional watchlist
# - Better embeds
# - Duplicate alert protection
# - Cleaner parsing
# ==========================================================

TXT_FILE = os.getenv("TXT_FILE", "decay.txt")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

ALERT_CHANNEL_ID_RAW = os.getenv("ALERT_CHANNEL_ID", "").strip()
ALERT_CHANNEL_ID = int(ALERT_CHANNEL_ID_RAW) if ALERT_CHANNEL_ID_RAW.isdigit() else None

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

ALERT_MINUTES = int(os.getenv("ALERT_MINUTES", "10"))
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "60"))

MENTION_EVERYONE = os.getenv(
    "MENTION_EVERYONE",
    "true"
).lower() in ("true", "1", "yes", "y")

WATCHLIST_RAW = os.getenv("WATCHLIST", "").strip()

WATCHLIST = {
    w.strip().upper()
    for w in WATCHLIST_RAW.split(",")
    if w.strip()
} if WATCHLIST_RAW else set()

ALERTED_FILE = "alerted.json"

JORDAN_TZ = ZoneInfo("Asia/Amman")


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

    reading_upcoming = False

    with open(TXT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()

            # Start reading after UPCOMING DECAYS
            if "UPCOMING DECAYS" in line:
                reading_upcoming = True
                continue

            # Ignore everything before UPCOMING DECAYS
            if not reading_upcoming:
                continue

            # Ignore garbage lines
            if (
                not line
                or "---" in line
                or "Charon Client" in line
                or "Discord:" in line
                or "Reference Time" in line
            ):
                continue

            # Must contain world | time | info
            if line.count("|") < 2:
                continue

            try:
                parts = [p.strip() for p in line.split("|")]

                world = parts[0].upper()
                utc_time_str = parts[1]

                utc_time = datetime.strptime(
                    utc_time_str,
                    "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=ZoneInfo("UTC"))

                jordan_time = utc_time.astimezone(JORDAN_TZ)

                now = datetime.now(JORDAN_TZ)

                # Skip already decayed worlds
                if jordan_time <= now:
                    continue

                # Optional watchlist
                if WATCHLIST and world not in WATCHLIST:
                    continue

                worlds.append((world, jordan_time))

            except Exception as e:
                print(f"[PARSE ERROR] {line} | {e}")

    worlds.sort(key=lambda item: item[1])

    return worlds


def get_upcoming_worlds(limit=5):
    now = datetime.now(JORDAN_TZ)

    upcoming = []

    for world, decay_time in parse_worlds():
        seconds_left = int((decay_time - now).total_seconds())

        if seconds_left >= 0:
            upcoming.append((world, decay_time, seconds_left))

    upcoming.sort(key=lambda item: item[2])

    return upcoming[:limit]


def make_decay_embed(
    world: str,
    decay_time: datetime,
    seconds_left: int,
    title="🌍 World Decay Alert"
):
    embed = discord.Embed(
        title=title,
        description=f"**`{world}`** is decaying soon.",
        color=0xFF3300
    )

    embed.add_field(
        name="🌍 World",
        value=f"`{world}`",
        inline=True
    )

    embed.add_field(
        name="⏳ Time Left",
        value=f"**{format_left(seconds_left)}**",
        inline=True
    )

    embed.add_field(
        name="🕒 Jordan Time",
        value=decay_time.strftime("%Y-%m-%d %I:%M:%S %p"),
        inline=False
    )

    embed.add_field(
        name="🚨 Alert Threshold",
        value=f"{ALERT_MINUTES} minutes",
        inline=True
    )

    embed.set_footer(
        text="Decay Bot v4 • Jordan Time"
    )

    return embed


def send_webhook_fallback(world, decay_time, seconds_left):
    if not DISCORD_WEBHOOK_URL:
        return False

    mention = "@everyone\n" if MENTION_EVERYONE else ""

    payload = {
        "content": f"{mention}🚨 **WORLD DECAY SOON: `{world}`**",
        "embeds": [
            {
                "title": "🌍 World Decay Alert",
                "description": f"`{world}` is decaying soon.",
                "color": 16724736,
                "fields": [
                    {
                        "name": "World",
                        "value": f"`{world}`",
                        "inline": True
                    },
                    {
                        "name": "Time Left",
                        "value": format_left(seconds_left),
                        "inline": True
                    },
                    {
                        "name": "Jordan Time",
                        "value": decay_time.strftime("%Y-%m-%d %I:%M:%S %p"),
                        "inline": False
                    }
                ]
            }
        ]
    }

    r = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=15
    )

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

        print("[OK] Slash commands synced globally.")


client = DecayClient()


async def send_bot_alert(world, decay_time, seconds_left):
    if not ALERT_CHANNEL_ID:
        return False

    channel = client.get_channel(ALERT_CHANNEL_ID)

    if channel is None:
        try:
            channel = await client.fetch_channel(ALERT_CHANNEL_ID)
        except Exception as e:
            print("[ERROR] Cannot fetch alert channel:", repr(e))
            return False

    mention = "@everyone\n" if MENTION_EVERYONE else ""

    embed = make_decay_embed(
        world,
        decay_time,
        seconds_left
    )

    try:
        await channel.send(
            content=f"{mention}🚨 **WORLD DECAY SOON: `{world}`**",
            embed=embed
        )

        return True

    except Exception as e:
        print("[ERROR] Alert failed:", repr(e))
        return False


async def auto_alert_loop():
    await client.wait_until_ready()

    alerted = load_alerted()

    while not client.is_closed():
        try:
            now = datetime.now(JORDAN_TZ)

            for world, decay_time in parse_worlds():
                seconds_left = int(
                    (decay_time - now).total_seconds()
                )

                if seconds_left < 0:
                    continue

                alert_key = f"{world}|{decay_time.isoformat()}"

                if alert_key in alerted:
                    continue

                if seconds_left <= ALERT_MINUTES * 60:
                    sent = await send_bot_alert(
                        world,
                        decay_time,
                        seconds_left
                    )

                    if not sent and DISCORD_WEBHOOK_URL:
                        try:
                            sent = send_webhook_fallback(
                                world,
                                decay_time,
                                seconds_left
                            )
                        except Exception as e:
                            print("[WEBHOOK ERROR]", repr(e))

                    if sent:
                        alerted.add(alert_key)
                        save_alerted(alerted)

                        print(
                            f"[SENT] {world} | "
                            f"{format_left(seconds_left)} left"
                        )

        except Exception as e:
            print("[AUTO ALERT ERROR]", repr(e))

        await asyncio.sleep(CHECK_EVERY_SECONDS)


@client.event
async def on_ready():
    print("====================================")
    print("Decay Bot v4 Started")
    print("====================================")
    print(f"Logged in as: {client.user}")
    print(f"TXT file: {TXT_FILE}")
    print(f"Worlds loaded: {len(parse_worlds())}")
    print(f"Alert threshold: {ALERT_MINUTES} minutes")
    print(f"Check interval: {CHECK_EVERY_SECONDS}s")
    print(
        f"Alert channel ID: "
        f"{ALERT_CHANNEL_ID if ALERT_CHANNEL_ID else 'Not set'}"
    )

    print(
        f"Webhook fallback: "
        f"{'ON' if DISCORD_WEBHOOK_URL else 'OFF'}"
    )

    print(f"Mention everyone: {MENTION_EVERYONE}")

    print(
        f"Watchlist: "
        f"{', '.join(sorted(WATCHLIST)) if WATCHLIST else 'All worlds'}"
    )

    print("Commands: /nearest, /test")


@client.tree.command(
    name="nearest",
    description="Shows nearest decaying worlds."
)
@app_commands.describe(
    count="How many worlds to show."
)
async def nearest(interaction: discord.Interaction, count: int = 5):
    count = max(1, min(count, 20))

    upcoming = get_upcoming_worlds(limit=count)

    if not upcoming:
        await interaction.response.send_message(
            "No upcoming worlds found.",
            ephemeral=True
        )
        return

    lines = []

    for index, (world, decay_time, seconds_left) in enumerate(upcoming, start=1):
        lines.append(
            f"**{index}. `{world}`**\n"
            f"⏳ Left: **{format_left(seconds_left)}**\n"
            f"🕒 `{decay_time.strftime('%Y-%m-%d %I:%M:%S %p')} Jordan time`"
        )

    embed = discord.Embed(
        title="🌍 Nearest Decaying Worlds",
        description="\n\n".join(lines),
        color=0xFF9900
    )

    embed.set_footer(
        text="Decay Bot v4 • Jordan Time"
    )

    await interaction.response.send_message(
        embed=embed
    )


@client.tree.command(
    name="test",
    description="Sends a test alert."
)
async def test(interaction: discord.Interaction):
    now = datetime.now(JORDAN_TZ)

    decay_time = now + timedelta(minutes=5)

    embed = make_decay_embed(
        "TESTWORLD",
        decay_time,
        300,
        title="🧪 Test Alert"
    )

    mention = "@everyone\n" if MENTION_EVERYONE else ""

    await interaction.response.send_message(
        content=f"{mention}🧪 TEST ALERT",
        embed=embed
    )


if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError(
            "Missing DISCORD_BOT_TOKEN environment variable."
        )

    # Reset old alerts automatically if worlds changed
    if not os.path.exists(ALERTED_FILE):
        with open(ALERTED_FILE, "w") as f:
            json.dump([], f)

    client.run(DISCORD_BOT_TOKEN)
