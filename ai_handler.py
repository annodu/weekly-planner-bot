"""OpenAI-powered natural language handler for the weekly planner bot."""
import logging
import os

from openai import OpenAI

import lists_store
import menu_store

log = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _make_tool(name: str, description: str, properties: dict, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOLS = [
    _make_tool("add_todo", "Add one or more items to the to-do list.", {
        "items": {"type": "array", "items": {"type": "string"}, "description": "List of to-do items to add."},
        "category": {"type": "string", "description": "Optional category, e.g. 'errands', 'work', 'health'."},
    }, ["items"]),
    _make_tool("remove_todo", "Remove a to-do item by name (partial match).", {
        "text": {"type": "string"},
    }, ["text"]),
    _make_tool("complete_todo", "Mark a to-do item as done.", {
        "text": {"type": "string"},
    }, ["text"]),
    _make_tool("show_todos", "Retrieve the current to-do list.", {}),
    _make_tool("add_shopping", "Add one or more items to the shopping list.", {
        "items": {"type": "array", "items": {"type": "string"}, "description": "List of things to buy."},
        "category": {"type": "string", "description": "Optional category, e.g. 'groceries', 'household'."},
    }, ["items"]),
    _make_tool("remove_shopping", "Remove an item from the shopping list by name (partial match).", {
        "text": {"type": "string"},
    }, ["text"]),
    _make_tool("mark_bought", "Mark a shopping item as bought/gotten.", {
        "text": {"type": "string"},
    }, ["text"]),
    _make_tool("clear_bought", "Clear all items already marked as bought from the shopping list.", {}),
    _make_tool("show_shopping", "Retrieve the current shopping list.", {}),
    _make_tool(
        "plan_week_from_todos",
        "Look at the full to-do list and suggest which items to tackle this week, taking into account the current weekly menu.",
        {},
    ),
    _make_tool("add_to_weekly_menu", "Add an item directly to this week's menu/plan.", {
        "item": {"type": "string"},
        "category": {"type": "string", "description": "Category: work, social, fitness, side_projects"},
    }, ["item"]),
    _make_tool("show_weekly_menu", "Show this week's menu/plan.", {}),
    _make_tool("mark_menu_done", "Mark a weekly menu item as done/completed (removes it from the active menu).", {
        "item": {"type": "string", "description": "Name or partial name of the menu item to mark done."},
    }, ["item"]),
]


def _execute_tool(name: str, inp: dict) -> str:
    if name == "add_todo":
        category = inp.get("category", "")
        added = [lists_store.add_todo(t, category) for t in inp["items"]]
        return f"Added {len(added)} to-do(s): {', '.join(i['text'] for i in added)}"

    if name == "remove_todo":
        ok = lists_store.remove_todo(inp["text"])
        return "Removed." if ok else f"Couldn't find '{inp['text']}' in to-dos."

    if name == "complete_todo":
        ok = lists_store.complete_todo(inp["text"])
        return "Marked done." if ok else f"Couldn't find '{inp['text']}' in to-dos."

    if name == "show_todos":
        return lists_store.format_todos()

    if name == "add_shopping":
        category = inp.get("category", "")
        added = [lists_store.add_shopping(t, category) for t in inp["items"]]
        return f"Added {len(added)} item(s): {', '.join(i['text'] for i in added)}"

    if name == "remove_shopping":
        ok = lists_store.remove_shopping(inp["text"])
        return "Removed." if ok else f"Couldn't find '{inp['text']}' in shopping list."

    if name == "mark_bought":
        ok = lists_store.mark_bought(inp["text"])
        return "Marked as bought." if ok else f"Couldn't find '{inp['text']}' in shopping list."

    if name == "clear_bought":
        n = lists_store.clear_bought()
        return f"Cleared {n} bought item(s)."

    if name == "show_shopping":
        return lists_store.format_shopping()

    if name == "plan_week_from_todos":
        todos = lists_store.load_todos()
        pending = [t for t in todos if not t["done"]]
        menu = menu_store.load_menu()
        menu_text = menu_store.format_full_menu(menu)
        pending_text = "\n".join(f"- {t['text']}" + (f" [{t['category']}]" if t.get("category") else "") for t in pending)
        return f"Current weekly menu:\n{menu_text}\n\nFull to-do backlog:\n{pending_text if pending_text else 'Empty'}"

    if name == "add_to_weekly_menu":
        menu = menu_store.load_menu()
        cat = inp.get("category", "work")
        menu = menu_store.add_item(inp["item"], menu, cat)
        return f"Added '{inp['item']}' to this week's menu under {cat}."

    if name == "show_weekly_menu":
        menu = menu_store.load_menu()
        return menu_store.format_full_menu(menu)

    if name == "mark_menu_done":
        menu = menu_store.load_menu()
        menu = menu_store.mark_done(inp["item"], menu)
        return f"Marked '{inp['item']}' as done on the weekly menu."

    return f"Unknown tool: {name}"


def _build_system_prompt() -> str:
    return (
        "You are Ann's personal weekly planner assistant on Telegram. "
        "Ann lives in London. You know her calendar, weekly menu, to-do list, and shopping list. "
        "Be concise, warm, and direct — no filler phrases. "
        "When Ann says something casually like 'add milk' or 'what should I do this week', "
        "use your tools to take action and then give her a brief, friendly confirmation. "
        "When she asks you to plan her week, look at her to-do backlog and suggest a realistic set "
        "of things to tackle, then offer to add them to her weekly menu. "
        "Format responses for Telegram Markdown. Keep replies short unless she asks for detail."
    )


async def handle_message(text: str, conversation_history: list[dict]) -> str:
    """
    Process a freeform message with GPT-4o. Returns the response text.
    conversation_history is a list of {"role": "user"|"assistant", "content": str} dicts.
    """
    import json

    client = _get_client()

    messages = (
        [{"role": "system", "content": _build_system_prompt()}]
        + conversation_history
        + [{"role": "user", "content": text}]
    )

    # Agentic loop — model may call multiple tools
    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            return msg.content or "Done."

        # Append assistant message with tool calls
        messages.append(msg)

        # Execute each tool and feed results back
        for tc in tool_calls:
            inp = json.loads(tc.function.arguments)
            result = _execute_tool(tc.function.name, inp)
            log.info("Tool %s(%s) -> %s", tc.function.name, inp, result[:100])
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
