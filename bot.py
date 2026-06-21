"""
Main bot entry point. Commands:
  /weekly  — trigger weekly menu builder
  /nudge   — trigger daily nudge
  /menu    — show current menu with emojis
  /add <item> — add an item to the menu
  /remove <item> — remove an item from the menu
  /done <item> — mark an item done
Freeform replies handled based on conversation state.
"""
import datetime
import json
import logging
import os
import random
import re

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import ai_handler
import calendar_client
import events_search
import gmail_reader
import lists_store
import menu_store

WATCHLIST_FILE = "watchlist.json"
VENUES_FILE = "venues.json"
WORK_KEYWORDS = ("anook", "row k", "build", "work", "design", "side project", "tiktok", "tik tok", "content")


def load_venues() -> list[dict]:
    if os.path.exists(VENUES_FILE):
        with open(VENUES_FILE) as f:
            return json.load(f)
    return []


def save_venues(venues: list[dict]) -> None:
    with open(VENUES_FILE, "w") as f:
        json.dump(venues, f, indent=2)


def suggest_venue() -> str:
    venues = load_venues()
    if not venues:
        return ""
    v = random.choice(venues)
    return f"📍 Where are you working from? How about *{v['name']}* ({v['area']})?"


def is_work_task(item: str) -> bool:
    return any(k in item.lower() for k in WORK_KEYWORDS)


def load_watchlist() -> list[dict]:
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE) as f:
            return json.load(f)
    return []


def save_watchlist(watchlist: list[dict]) -> None:
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f, indent=2)


def fetch_event_name(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
        if match:
            title = match.group(1)
            for suffix in [" · Luma", " | Eventbrite", " Tickets", " - Eventbrite"]:
                title = title.replace(suffix, "")
            return title.strip()
    except Exception:
        pass
    return url


def extract_event_url(text: str):
    match = re.search(
        r"(https?://(?:lu\.ma|luma\.com|(?:www\.)?eventbrite\.co\.uk|(?:www\.)?eventbrite\.com)/[^\s]+)",
        text,
    )
    if match:
        return match.group(1).rstrip("?&")
    return None

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

AWAITING_WEEKLY_CONFIRM = "weekly_confirm"
AWAITING_DAILY_PICK = "daily"
_state: dict[int, str] = {}

# Per-chat short conversation history for Claude (last N turns)
_history: dict[int, list[dict]] = {}
MAX_HISTORY = 10


# ── helpers ───────────────────────────────────────────────────────────────────

def _gcal():
    return calendar_client.get_calendar_service()


async def _send(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


def _is_ann(update: Update) -> bool:
    return update.effective_chat.id == CHAT_ID


def _infer_category(item: str) -> str:
    lower = item.lower()
    if any(k in lower for k in ("gym", "run", "yoga", "walk", "swim", "fitness")):
        return "fitness"
    if any(k in lower for k in ("dinner", "drinks", "lunch", "social", "friend", "party", "event", "🎟")):
        return "social"
    if any(k in lower for k in ("tiktok", "tik tok", "blog", "clean", "row k", "content")):
        return "side_projects"
    return "work"


# ── weekly flow ───────────────────────────────────────────────────────────────

async def run_weekly(context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("Running weekly menu builder")
    try:
        service = _gcal()
        today = datetime.date.today()
        monday = today + datetime.timedelta(days=(7 - today.weekday()) % 7)
        cal_events = calendar_client.get_week_events(service, monday)
        week_summary = calendar_client.summarise_week(cal_events)
    except Exception as e:
        week_summary = f"_(couldn't load calendar: {e})_"

    suggestions = events_search.search_london_events(days_ahead=7)
    menu = menu_store.reset_menu(suggestions)
    event_text = events_search.format_event_suggestions(suggestions)
    menu_text = menu_store.format_full_menu(menu)

    msg = (
        "🗓 *New week. Here's what's on your plate:*\n\n"
        f"{menu_text}\n\n"
        f"*Calendar:*\n{week_summary}\n\n"
        f"*Events in London this week* (don't just say you'll go):\n{event_text}\n\n"
        "Reply to add or remove anything:\n"
        "• _'add yoga Tuesday'_ or _'remove clean'_\n"
        "• Or just say *looks good* to confirm as is."
    )
    await _send(context, msg)
    _state[CHAT_ID] = AWAITING_WEEKLY_CONFIRM


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    await run_weekly(context)


# ── daily nudge ───────────────────────────────────────────────────────────────

async def run_daily_nudge(context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("Running daily nudge")
    try:
        service = _gcal()
        free_summary = calendar_client.get_today_free_slots(service)
    except Exception as e:
        free_summary = f"_(couldn't load calendar: {e})_"

    menu = menu_store.load_menu()
    pending = menu_store.pending_items(menu)
    todays_events = menu_store.todays_event_suggestions(menu)

    if not pending and not todays_events:
        await _send(context, "✅ Menu's clear — nothing left this week. Add more with /weekly.")
        return

    menu_text = menu_store.format_full_menu(menu)

    event_nudge = ""
    if todays_events:
        event_nudge = "\n⚡ *Happening today:*\n"
        for e in todays_events:
            event_nudge += f"🎟️ *{e['name']}* — {e['date']}\n{e['link']}\n"

    msg = (
        f"*{datetime.date.today().strftime('%A')}* — {free_summary}\n"
        f"{event_nudge}\n"
        f"*This week's menu:*\n{menu_text}\n\n"
        "What are you doing this evening? Reply with the number, name, or *skip*."
    )
    await _send(context, msg)
    _state[CHAT_ID] = AWAITING_DAILY_PICK


async def cmd_nudge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    await run_daily_nudge(context)


# ── event alert poller ────────────────────────────────────────────────────────

async def poll_new_events(context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("Polling for new events")
    all_events = events_search.search_london_events(days_ahead=60)
    new_events = menu_store.filter_new_events(all_events)

    if new_events:
        lines = []
        for e in new_events[:5]:
            lines.append(f"• *{e['name']}* — {e['date']}\n  {e['link']}")
        await _send(
            context,
            "📍 *New London events just announced:*\n\n"
            + "\n".join(lines)
            + "\n\nSend me the link if you want to watch for similar ones.",
        )

    # Also scan newsletters
    try:
        creds = calendar_client.get_gmail_creds()
        findings = gmail_reader.check_newsletters(creds)
        if findings:
            msg = gmail_reader.format_newsletter_findings(findings)
            await _send(context, msg)
    except Exception as e:
        log.warning(f"Gmail newsletter scan failed: {e}")


# ── /add ─────────────────────────────────────────────────────────────────────

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    item = " ".join(context.args).strip()
    if not item:
        await update.message.reply_text("Usage: /add <item>  e.g. /add yoga Tuesday")
        return
    menu = menu_store.load_menu()
    cat = _infer_category(item)
    menu = menu_store.add_item(item, menu, cat)
    menu_text = menu_store.format_full_menu(menu)
    await update.message.reply_text(
        f"✅ Added to {cat.replace('_', ' ')}: _{item}_\n\n*Updated menu:*\n{menu_text}",
        parse_mode="Markdown",
    )


# ── /remove ───────────────────────────────────────────────────────────────────

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    item = " ".join(context.args).strip()
    if not item:
        await update.message.reply_text("Usage: /remove <item>  e.g. /remove clean")
        return
    menu = menu_store.load_menu()
    menu, found = menu_store.remove_item(item, menu)
    if found:
        menu_text = menu_store.format_full_menu(menu)
        await update.message.reply_text(
            f"🗑️ Removed: _{item}_\n\n*Updated menu:*\n{menu_text}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"Couldn't find _{item}_ on the menu. Check /menu for exact names.",
            parse_mode="Markdown",
        )


# ── /done ─────────────────────────────────────────────────────────────────────

async def cmd_spot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    venues = load_venues()
    if not venues:
        await update.message.reply_text("No spots saved yet. Use /addspot <name>, <area> to add one.")
        return
    v = random.choice(venues)
    notes = f"\n_{v['notes']}_" if v.get("notes") else ""
    await update.message.reply_text(
        f"📍 *{v['name']}*\n{v['area']} — {v['vibe']}{notes}\n\n"
        f"Want another? Run /spot again.",
        parse_mode="Markdown",
    )


async def cmd_spots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    venues = load_venues()
    if not venues:
        await update.message.reply_text("No spots saved yet. Use /addspot <name>, <area> to add one.")
        return
    lines = ["📍 *Your work spots:*\n"]
    for i, v in enumerate(venues, 1):
        lines.append(f"{i}. *{v['name']}* — {v['area']} ({v['vibe']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_addspot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Usage: /addspot <name>, <area>\ne.g. /addspot Ace Hotel, Shoreditch"
        )
        return
    parts = [p.strip() for p in text.split(",", 1)]
    name = parts[0]
    area = parts[1] if len(parts) > 1 else "London"
    venues = load_venues()
    venues.append({"name": name, "area": area, "vibe": "café/lobby", "notes": ""})
    save_venues(venues)
    await update.message.reply_text(
        f"✅ Added *{name}* ({area}) to your spots.\nRun /spots to see the full list.",
        parse_mode="Markdown",
    )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    watchlist = load_watchlist()
    if not watchlist:
        await update.message.reply_text("Watchlist is empty. Send me a Luma link and I'll watch for similar events.")
        return
    lines = [f"👀 *Watching for events like:*\n"]
    for w in watchlist:
        lines.append(f"• *{w['name']}*\n  {w['link']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_todos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    text = lists_store.format_todos()
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_shopping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    text = lists_store.format_shopping()
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    item = " ".join(context.args).strip()
    if not item:
        await update.message.reply_text("Usage: /done <item name>")
        return
    menu = menu_store.load_menu()
    menu = menu_store.mark_done(item, menu)
    await update.message.reply_text(f"✅ Done: _{item}_", parse_mode="Markdown")


# ── /menu ─────────────────────────────────────────────────────────────────────

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_ann(update): return
    menu = menu_store.load_menu()
    menu_text = menu_store.format_full_menu(menu)
    done = menu["done"]

    msg = f"*Menu — week of {menu['week_of']}*\n\n{menu_text}"
    if done:
        done_lines = "  ".join(f"✅ {d}" for d in done)
        msg += f"\n\n*Done this week:* {done_lines}"

    await update.message.reply_text(msg, parse_mode="Markdown")


# ── freeform reply handler ────────────────────────────────────────────────────

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return

    text = update.message.text.strip()

    # Detect event links (Luma or Eventbrite) — handle before AI so the URL isn't mangled
    event_url = extract_event_url(text)
    if event_url:
        event_name = fetch_event_name(event_url)
        watchlist = load_watchlist()
        already = any(w["link"] == event_url for w in watchlist)
        if not already:
            watchlist.append({"name": event_name, "link": event_url, "added": datetime.date.today().isoformat()})
            save_watchlist(watchlist)
        await update.message.reply_text(
            f"👀 Got it — watching for events like *{event_name}*.\n"
            f"I'll alert you as soon as something similar is announced.\n\n"
            f"Use /watchlist to see everything I'm tracking.",
            parse_mode="Markdown",
        )
        return

    # Route everything else through Claude
    history = _history.get(CHAT_ID, [])
    try:
        reply = await ai_handler.handle_message(text, history)
    except Exception as e:
        log.error("AI handler error: %s", e, exc_info=True)
        reply = f"Error: {e}"

    # Update rolling history
    history = history + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ]
    _history[CHAT_ID] = history[-MAX_HISTORY:]

    # Clear any pending state — Claude handles context now
    _state.pop(CHAT_ID, None)

    await update.message.reply_text(reply, parse_mode="Markdown")


# ── scheduled jobs ────────────────────────────────────────────────────────────

def schedule_jobs(app: Application) -> None:
    jq = app.job_queue

    # Weekly menu: Sunday 18:00 (temporarily set to 20:40 for testing)
    jq.run_daily(run_weekly, time=datetime.time(20, 40), days=(6,))

    # Daily nudge: 13:00 every day
    jq.run_daily(run_daily_nudge, time=datetime.time(13, 0))

    # Event poller: every 6 hours (alerts for newly announced events)
    jq.run_repeating(poll_new_events, interval=60 * 60 * 6, first=30)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("weekly", cmd_weekly))
    app.add_handler(CommandHandler("nudge", cmd_nudge))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("todos", cmd_todos))
    app.add_handler(CommandHandler("shopping", cmd_shopping))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("spot", cmd_spot))
    app.add_handler(CommandHandler("spots", cmd_spots))
    app.add_handler(CommandHandler("addspot", cmd_addspot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply))

    schedule_jobs(app)

    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
