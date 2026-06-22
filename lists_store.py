"""Persistent to-do and shopping list management."""
import json
import os
from datetime import date

_DATA_DIR = os.getenv("DATA_DIR", ".")
TODO_FILE = os.path.join(_DATA_DIR, "todo_list.json")
SHOPPING_FILE = os.path.join(_DATA_DIR, "shopping_list.json")


def _load(path: str) -> list[dict]:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save(path: str, items: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(items, f, indent=2)


# ── to-do ────────────────────────────────────────────────────────────────────

def load_todos() -> list[dict]:
    return _load(TODO_FILE)


def save_todos(items: list[dict]) -> None:
    _save(TODO_FILE, items)


def add_todo(text: str, category: str = "") -> dict:
    items = load_todos()
    item = {"text": text, "category": category, "done": False, "added": date.today().isoformat()}
    items.append(item)
    save_todos(items)
    return item


def remove_todo(text: str) -> bool:
    items = load_todos()
    lower = text.lower()
    new_items = [i for i in items if lower not in i["text"].lower()]
    if len(new_items) == len(items):
        return False
    save_todos(new_items)
    return True


def complete_todo(text: str) -> bool:
    items = load_todos()
    lower = text.lower()
    found = False
    for item in items:
        if lower in item["text"].lower():
            item["done"] = True
            found = True
    if found:
        save_todos(items)
    return found


def format_todos() -> str:
    items = load_todos()
    pending = [i for i in items if not i["done"]]
    done = [i for i in items if i["done"]]

    if not pending and not done:
        return "No to-dos yet."

    cat_map: dict[str, list[str]] = {}
    for item in pending:
        cat = (item.get("category") or "Other").strip().title() or "Other"
        cat_map.setdefault(cat, []).append(item["text"])

    lines = ["*Here's your to-do list:*\n"]
    for cat in sorted(cat_map):
        lines.append(f"*{cat}:*")
        for text in cat_map[cat]:
            lines.append(f"  • {text}")
        lines.append("")

    if done:
        lines.append("*Done:*")
        for item in done:
            lines.append(f"  ✅ {item['text']}")

    return "\n".join(lines)


# ── shopping ──────────────────────────────────────────────────────────────────

def load_shopping() -> list[dict]:
    return _load(SHOPPING_FILE)


def save_shopping(items: list[dict]) -> None:
    _save(SHOPPING_FILE, items)


def add_shopping(text: str, category: str = "") -> dict:
    items = load_shopping()
    item = {"text": text, "category": category, "bought": False, "added": date.today().isoformat()}
    items.append(item)
    save_shopping(items)
    return item


def remove_shopping(text: str) -> bool:
    items = load_shopping()
    lower = text.lower()
    new_items = [i for i in items if lower not in i["text"].lower()]
    if len(new_items) == len(items):
        return False
    save_shopping(new_items)
    return True


def mark_bought(text: str) -> bool:
    items = load_shopping()
    lower = text.lower()
    found = False
    for item in items:
        if lower in item["text"].lower():
            item["bought"] = True
            found = True
    if found:
        save_shopping(items)
    return found


def clear_bought() -> int:
    items = load_shopping()
    remaining = [i for i in items if not i["bought"]]
    removed = len(items) - len(remaining)
    if removed:
        save_shopping(remaining)
    return removed


def format_shopping() -> str:
    items = load_shopping()
    needed = [i for i in items if not i["bought"]]
    bought = [i for i in items if i["bought"]]

    if not needed and not bought:
        return "Shopping list is empty."

    cat_map: dict[str, list[str]] = {}
    for item in needed:
        cat = (item.get("category") or "Other").strip().title() or "Other"
        cat_map.setdefault(cat, []).append(item["text"])

    lines = ["*Here's your shopping list:*\n"]
    for cat in sorted(cat_map):
        lines.append(f"*{cat}:*")
        for text in cat_map[cat]:
            lines.append(f"  • {text}")
        lines.append("")

    if bought:
        lines.append("*Got it:*")
        for item in bought:
            lines.append(f"  ✅ {item['text']}")

    return "\n".join(lines)
