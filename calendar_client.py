import base64
import datetime
import json
import os
import pickle
import tempfile

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
TOKEN_FILE = "token.pickle"


def get_calendar_service():
    creds = _load_creds()
    return build("calendar", "v3", credentials=creds)


def get_gmail_creds():
    return _load_creds()


def _load_creds():
    creds = None

    # Try env var first (Railway), then local file (Mac)
    token_b64 = os.getenv("GOOGLE_TOKEN_B64")
    if token_b64:
        creds = pickle.loads(base64.b64decode(token_b64))
    elif os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_creds(creds)
        return creds

    # On Railway there's no browser for interactive OAuth — raise clearly
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json and not os.path.exists(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")):
        raise RuntimeError(
            "No valid Google token and no credentials file found. "
            "Run setup_google_auth.py locally and update GOOGLE_TOKEN_B64 in Railway."
        )

    if creds_json:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            creds_file = f.name
    else:
        creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_creds(creds)
    return creds


def _save_creds(creds):
    # Save locally if possible
    try:
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    except Exception:
        pass
    # Print the base64 token so it can be copied to Railway env vars
    b64 = base64.b64encode(pickle.dumps(creds)).decode()
    print(f"\n[INFO] Updated GOOGLE_TOKEN_B64 (copy this to Railway):\n{b64}\n")


def get_week_events(service, start_date: datetime.date) -> list[dict]:
    end_date = start_date + datetime.timedelta(days=7)
    time_min = datetime.datetime.combine(start_date, datetime.time.min).isoformat() + "Z"
    time_max = datetime.datetime.combine(end_date, datetime.time.min).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])


def get_today_free_slots(service) -> str:
    today = datetime.date.today()
    now = datetime.datetime.utcnow()
    end_of_day = datetime.datetime.combine(today, datetime.time(23, 59)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat() + "Z",
        timeMax=end_of_day,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return "the rest of the day free"

    busy_times = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end = e["end"].get("dateTime", e["end"].get("date", ""))
        summary = e.get("summary", "event")
        if "T" in start:
            start_fmt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%-I:%M%p")
            end_fmt = datetime.datetime.fromisoformat(end.replace("Z", "+00:00")).strftime("%-I:%M%p")
            busy_times.append(f"{summary} ({start_fmt}–{end_fmt})")
        else:
            busy_times.append(f"{summary} (all day)")

    return f"events: {', '.join(busy_times)}"


def summarise_week(events: list[dict]) -> str:
    if not events:
        return "No calendar events this week — wide open!"

    by_day: dict[str, list[str]] = {}
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        summary = e.get("summary", "event")
        if "T" in start:
            day = datetime.datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%A %-d %b")
        else:
            day = datetime.datetime.fromisoformat(start).strftime("%A %-d %b")
        by_day.setdefault(day, []).append(summary)

    lines = []
    for day, items in by_day.items():
        lines.append(f"• *{day}*: {', '.join(items)}")
    return "\n".join(lines)
