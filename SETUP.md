# Weekly Planner Bot — Setup Guide

## 1. Create your Telegram bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow the prompts, copy the **bot token**
3. Send any message to your new bot (so it has a chat to respond to)

## 2. Install dependencies

```bash
cd weekly-planner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
- `TELEGRAM_BOT_TOKEN` — paste the token from BotFather
- `TELEGRAM_CHAT_ID` — find it in step 4 below
- `EVENT_INTERESTS` — comma-separated keywords: `AI,ML,Python,startups,design`
- `EVENT_AREAS` — e.g. `London,East London`
- `FREE_EVENINGS` — e.g. `Tuesday,Wednesday,Thursday`

## 4. Find your Telegram chat ID

```bash
python get_chat_id.py
```

Paste the number into `TELEGRAM_CHAT_ID` in `.env`.

## 5. Set up Google Calendar

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Desktop app) → download as `credentials.json`
4. Place `credentials.json` in this folder
5. Authenticate once:

```bash
python setup_google_auth.py
```

A browser window opens; log in and allow access. `token.pickle` is saved.

## 6. Run the bot

```bash
python bot.py
```

Bot runs continuously, polls Telegram for messages, and fires scheduled jobs.

## 7. Commands

| Command | What it does |
|---|---|
| `/weekly` | Manually trigger the weekly menu builder |
| `/nudge` | Manually trigger today's nudge |
| `/menu` | Show current week's menu and done items |
| `/done <item>` | Mark an item as done |

The bot will automatically:
- **Sunday 6pm** — send the weekly menu prompt
- **Daily 12pm** — send the daily nudge

## 8. Hosting (always-on)

**Cheapest option — a $5/mo VPS (DigitalOcean, Hetzner, etc.):**

```bash
# On the VPS, after cloning and setting up:
pip install -r requirements.txt
# Create a systemd service or use tmux/screen
tmux new -s planner
python bot.py
# Ctrl+B D to detach
```

**Or use a process manager:**
```bash
pip install supervisor
# Add a supervisor config pointing to python bot.py
```

**Raspberry Pi at home:** same steps, runs indefinitely on your local network.

## Files

- `bot.py` — main bot, all commands and scheduled jobs
- `calendar_client.py` — Google Calendar API wrapper
- `events_search.py` — Luma event search
- `menu_store.py` — read/write `menu.json`
- `menu.json` — auto-created, stores the week's menu
- `token.pickle` — Google auth token (auto-created, don't share)
- `credentials.json` — Google OAuth credentials (don't share or commit)
