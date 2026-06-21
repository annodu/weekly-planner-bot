"""Persistent to-do and shopping list management."""
import json
import os
from datetime import date

TODO_FILE = "todo_list.json"
SHOPPING_FILE = "shopping_list.json"


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
    if not items:
        return "No to-dos yet."
    pending = [i for i in items if not i["done"]]
    done = [i for i in items if i["done"]]
    lines = []
    if pending:
        lines.append("*Pending:*")
        for i, item in enumerate(pending, 1):
            cat = f" [{item['category']}]" if item.get("category") else ""
            lines.append(f"{i}. {item['text']}{cat}")
    if done:
        lines.append("\n*Done:*")
        for item in done:
            lines.append(f"✅ {item['text']}")
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
    if not items:
        return "Shopping list is empty."
    needed = [i for i in items if not i["bought"]]
    bought = [i for i in items if i["bought"]]
    lines = []
    if needed:
        lines.append("*To buy:*")
        for i, item in enumerate(needed, 1):
            cat = f" [{item['category']}]" if item.get("category") else ""
            lines.append(f"{i}. {item['text']}{cat}")
    if bought:
        lines.append("\n*Got it:*")
        for item in bought:
            lines.append(f"✅ {item['text']}")
    return "\n".join(lines)
