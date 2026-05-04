# Decay Discord Alert Bot v2

This bot reads `decay.txt`, calculates decay times from:

**May 4, 2026 — 6:13 PM Jordan time**

Then sends a nice Discord webhook embed with:

- @everyone mention
- world name
- time left
- exact decay time in Jordan time
- alert threshold
- source file time

## Discord Webhook

No bot token needed.

1. Discord channel settings
2. Integrations
3. Webhooks
4. New Webhook
5. Copy webhook URL

## Run on Windows

```bat
pip install -r requirements.txt
set DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_HERE
python bot.py
```

## Run on Linux / Oracle

```bash
sudo apt update
sudo apt install -y python3 python3-venv unzip
mkdir -p ~/decaybot
cd ~/decaybot
# upload/extract files here
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="YOUR_WEBHOOK_HERE"
python bot.py
```

## Optional settings

Alert 30 minutes before decay:

```bash
export ALERT_MINUTES=30
```

Disable @everyone:

```bash
export MENTION_EVERYONE=false
```

Only alert certain worlds:

```bash
export WATCHLIST="REPLY,SPECIAL,AMMAN"
```

## Run 24/7 with systemd

Edit `decaybot.service` and replace:

`PUT_YOUR_WEBHOOK_HERE`

Then:

```bash
sudo cp decaybot.service /etc/systemd/system/decaybot.service
sudo systemctl daemon-reload
sudo systemctl enable decaybot
sudo systemctl start decaybot
sudo systemctl status decaybot
```

View logs:

```bash
journalctl -u decaybot -f
```
