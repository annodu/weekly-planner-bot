import json
import datetime
import os

MENU_FILE = os.getenv("MENU_FILE", "menu.json")
SEEN_EVENTS_FILE = "seen_events.json"

EMOJI_MAP = [
    ("anook", "💻"),
    ("row k", "💻"),
    ("tiktok", "🤳"),
    ("tik tok", "🤳"),
    ("content creation", "🤳"),
    ("gym", "🏋️‍♀️"),
    ("run", "🏃‍♀️"),
    ("yoga", "🧘‍♀️"),
    ("clean", "🧹"),
    ("dinner", "🍽️"),
    ("lunch", "🍽️"),
    ("drinks", "🍸"),
    ("social", "👯‍♀️"),
    ("event", "🎟️"),
    ("blog", "✍️"),
    ("write", "✍️"),
    ("read", "📖"),
    ("design", "🎨"),
    ("film", "🎬"),
    ("walk", "🚶‍♀️"),
]


def emoji_for(item: str) -> str:
    lower = item.lower()
    for keyword, emoji in EMOJI_MAP:
        if keyword in lower:
            return emoji
    return "•"


def format_menu_item(item: str, index: int) -> str:
    return f"{index}. {emoji_for(item)} {item}"


def _empty_menu(week_of: str) -> dict:
    return {
        "week_of": week_of,
        "work": [],
        "social": [],
        "fitness": [],
        "side_projects": [],
        "event_suggestions": [],
        "done": [],
        "picked_today": None,
    }


def load_menu() -> dict:
    if os.path.exists(MENU_FILE):
        with open(MENU_FILE) as f:
            return json.load(f)
    week_of = _current_week_monday()
    return _empty_menu(week_of)


def save_menu(menu: dict) -> None:
    with open(MENU_FILE, "w") as f:
        json.dump(menu, f, indent=2)


def _current_week_monday() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def _load_recurring() -> dict:
    cats = {
        "work": "RECURRING_WORK",
        "social": "RECURRING_SOCIAL",
        "fitness": "RECURRING_FITNESS",
        "side_projects": "RECURRING_SIDE_PROJECTS",
    }
    result = {}
    for cat, env_key in cats.items():
        raw = os.getenv(env_key, "")
        result[cat] = [i.strip() for i in raw.split(",") if i.strip()]
    return result


def reset_menu(event_suggestions: list[dict]) -> dict:
    menu = _empty_menu(_current_week_monday())
    menu["event_suggestions"] = event_suggestions
    recurring = _load_recurring()
    for cat, items in recurring.items():
        menu[cat] = list(items)
    save_menu(menu)
    return menu


def format_full_menu(menu: dict) -> str:
    all_items = pending_items(menu)
    if not all_items:
        return "_Nothing on the menu yet._"
    # Collapse duplicates into "Item x2" style
    counts: dict[str, int] = {}
    for item in all_items:
        counts[item] = counts.get(item, 0) + 1
    seen: set[str] = set()
    lines = []
    i = 1
    for item in all_items:
        if item in seen:
            continue
        seen.add(item)
        count = counts[item]
        label = f"{item} x{count}" if count > 1 else item
        lines.append(format_menu_item(label, i))
        i += 1
    return "\n".join(lines)


def add_item(item: str, menu: dict, category: str = "work") -> dict:
    if item not in menu[category]:
        menu[category].append(item)
    save_menu(menu)
    return menu


def remove_item(item: str, menu: dict) -> tuple[dict, bool]:
    for cat in ("work", "social", "fitness", "side_projects"):
        items_lower = [x.lower() for x in menu[cat]]
        if item.lower() in items_lower:
            idx = items_lower.index(item.lower())
            menu[cat].pop(idx)
            save_menu(menu)
            return menu, True
    return menu, False


def update_menu_from_reply(reply: str, menu: dict) -> dict:
    category_map = {
        "work": "work",
        "social": "social",
        "fitness": "fitness",
        "side project": "side_projects",
        "side projects": "side_projects",
        "project": "side_projects",
        "projects": "side_projects",
    }

    current_cat = None
    for line in reply.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.rstrip(":").lower()
        if lower in category_map:
            current_cat = category_map[lower]
            continue
        for key, cat in category_map.items():
            if line.lower().startswith(key + ":"):
                items_str = line[len(key) + 1:].strip()
                items = [i.strip() for i in items_str.split(",") if i.strip()]
                menu[cat].extend(items)
                current_cat = cat
                break
        else:
            if current_cat:
                items = [i.strip() for i in line.split(",") if i.strip()]
                menu[current_cat].extend(items)

    save_menu(menu)
    return menu


def mark_done(item: str, menu: dict) -> dict:
    lower = item.lower()
    for cat in ("work", "social", "fitness", "side_projects"):
        # substring match so "yoga" hits "Yoga Tuesday"
        matches = [i for i, x in enumerate(menu[cat]) if lower in x.lower()]
        for idx in reversed(matches):
            actual = menu[cat].pop(idx)
            if actual not in menu["done"]:
                menu["done"].append(actual)
    menu["picked_today"] = item
    save_menu(menu)
    return menu


def pending_items(menu: dict) -> list[str]:
    items = []
    for cat in ("work", "social", "fitness", "side_projects"):
        items.extend(menu[cat])
    return items


def todays_event_suggestions(menu: dict) -> list[dict]:
    today = datetime.date.today().strftime("%A")
    return [e for e in menu.get("event_suggestions", []) if today.lower() in e.get("date", "").lower()]


# ── seen events tracking (for future event alerts) ───────────────────────────

def load_seen_events() -> set[str]:
    if os.path.exists(SEEN_EVENTS_FILE):
        with open(SEEN_EVENTS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_events(seen: set[str]) -> None:
    with open(SEEN_EVENTS_FILE, "w") as f:
        json.dump(list(seen), f)


def filter_new_events(events: list[dict]) -> list[dict]:
    seen = load_seen_events()
    new = [e for e in events if e["link"] not in seen]
    seen.update(e["link"] for e in events)
    save_seen_events(seen)
    return new
