import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
TOKEN_FILE = "token.pickle"


def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds)


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
