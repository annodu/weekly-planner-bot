"""
Scan Gmail for event links from trusted newsletter senders.
Returns new links not previously seen.
"""
import base64
import json
import os
import re

from googleapiclient.discovery import build

SEEN_EMAIL_EVENTS_FILE = "seen_email_events.json"

def _newsletter_senders() -> list[str]:
    raw = os.getenv(
        "NEWSLETTER_SENDERS",
        "valerie@blackinfintech.co.uk,noreply@luma-mail.com,info@wearethekickback.com,noreply@tickxts.com,noreply@reminder.eventbrite.com",
    )
    return [s.strip().strip(">") for s in raw.split(",") if s.strip()]

EVENT_LINK_PATTERN = re.compile(
    r"https?://(?:"
    r"lu\.ma/[a-zA-Z0-9_-]+"
    r"|luma\.com/[a-zA-Z0-9_-]+"
    r"|(?:www\.)?eventbrite\.co\.uk/e/[^\s\"'>]+"
    r"|(?:www\.)?eventbrite\.com/e/[^\s\"'>]+"
    r"|tickxts\.com/e/[^\s\"'>]+"
    r"|wearethekickback\.com[^\s\"'>]*"
    r")"
)


def _load_seen() -> set:
    if os.path.exists(SEEN_EMAIL_EVENTS_FILE):
        with open(SEEN_EMAIL_EVENTS_FILE) as f:
            return set(json.load(f))
    return set()


def _save_seen(seen: set) -> None:
    with open(SEEN_EMAIL_EVENTS_FILE, "w") as f:
        json.dump(list(seen), f)


def _decode_body(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    # multipart — recurse into parts
    text = ""
    for sub in part.get("parts", []):
        text += _decode_body(sub)
    return text


def _extract_links(body: str) -> list[str]:
    return list({m.group(0).rstrip(".,)>\"'") for m in EVENT_LINK_PATTERN.finditer(body)})


def _sender_query() -> str:
    return " OR ".join(f"from:{s}" for s in _newsletter_senders())


def check_newsletters(gmail_creds) -> list[dict]:
    """
    Returns list of {subject, link, sender} for new event links found in emails.
    """
    service = build("gmail", "v1", credentials=gmail_creds)
    seen = _load_seen()
    found = []

    query = f"({_sender_query()}) newer_than:7d"
    results = service.users().messages().list(
        userId="me", q=query, maxResults=30
    ).execute()

    messages = results.get("messages", [])
    for msg_ref in messages:
        msg_id = msg_ref["id"]
        if msg_id in seen:
            continue

        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "")

        body = _decode_body(msg["payload"])
        links = _extract_links(body)

        for link in links:
            if link not in seen:
                found.append({
                    "subject": subject,
                    "sender": sender,
                    "link": link,
                })
                seen.add(link)

        seen.add(msg_id)

    _save_seen(seen)
    return found


def format_newsletter_findings(findings: list[dict]) -> str:
    if not findings:
        return ""
    lines = ["📧 *Events from your newsletters:*\n"]
    for f in findings:
        lines.append(f"• {f['link']}\n  _{f['subject']}_")
    return "\n".join(lines)
