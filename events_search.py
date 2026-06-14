"""
Search for London events via:
1. Meetup GraphQL API (no auth required)
2. Luma London discover page scrape
"""
import os
import datetime
import requests
import json


def _meetup_events(interests: list[str], days_ahead: int = 7) -> list[dict]:
    found = []
    end_dt = datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)

    for keyword in interests[:4]:
        try:
            query = """
            query($query: String!) {
              keywordSearch(
                input: { query: $query, lat: 51.5074, lon: -0.1278, radius: 15 }
                filter: { isOnline: false }
              ) {
                edges {
                  node {
                    result {
                      ... on Event {
                        title
                        eventUrl
                        dateTime
                        endTime
                        venue { city country }
                        group { name }
                      }
                    }
                  }
                }
              }
            }
            """
            resp = requests.post(
                "https://www.meetup.com/gql",
                json={"query": query, "variables": {"query": f"{keyword} London"}},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            edges = (
                resp.json()
                .get("data", {})
                .get("keywordSearch", {})
                .get("edges", [])
            )
            for edge in edges:
                result = edge.get("node", {}).get("result", {})
                title = result.get("title", "")
                url = result.get("eventUrl", "")
                date_str = result.get("dateTime", "")
                venue = result.get("venue") or {}
                city = venue.get("city", "")

                if not title or not date_str:
                    continue
                if city and "london" not in city.lower():
                    continue

                try:
                    dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    now = datetime.datetime.now(tz=dt.tzinfo)
                    cutoff = end_dt.replace(tzinfo=dt.tzinfo)
                    if now < dt < cutoff:
                        found.append({
                            "name": title,
                            "date": dt.strftime("%A %-d %b, %-I%p"),
                            "link": url,
                            "source": "Meetup",
                        })
                except Exception:
                    pass
        except Exception:
            pass

    return found


DEFAULT_LUMA_PAGES = "https://lu.ma/london,https://lu.ma/tech,https://lu.ma/ai,https://lu.ma/arts,https://lu.ma/food"


def _luma_pages() -> list[str]:
    raw = os.getenv("LUMA_PAGES", DEFAULT_LUMA_PAGES)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _scrape_luma_page(url: str, interests: list[str], cutoff: datetime.datetime) -> list[dict]:
    found = []
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return found

        text = resp.text
        marker = '"events":'
        start = text.find(marker)
        if start == -1:
            return found

        arr_start = text.find("[", start)
        if arr_start == -1:
            return found

        depth = 0
        arr_end = arr_start
        for i, ch in enumerate(text[arr_start:], arr_start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    arr_end = i
                    break

        events_json = json.loads(text[arr_start:arr_end + 1])

        for item in events_json:
            event = item.get("event") or item
            name = event.get("name", "")
            start_at = event.get("start_at", "")
            slug = event.get("url", "") or event.get("slug", "")
            geo = item.get("geo_address_json") or event.get("geo_address_json") or {}
            city = geo.get("city", "")

            if not name or not start_at:
                continue
            # For non-London pages, still filter to London events where city is known
            if city and "london" not in city.lower():
                continue

            try:
                dt = datetime.datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                now = datetime.datetime.now(tz=dt.tzinfo)
                cutoff_tz = cutoff.replace(tzinfo=dt.tzinfo)
                if now < dt < cutoff_tz:
                    link = slug if slug.startswith("http") else f"https://lu.ma/{slug}"
                    found.append({
                        "name": name,
                        "date": dt.strftime("%A %-d %b, %-I%p"),
                        "link": link,
                        "source": "Luma",
                    })
            except Exception:
                pass
    except Exception:
        pass
    return found


def _luma_events(interests: list[str], days_ahead: int = 60) -> list[dict]:
    cutoff = datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)
    found = []
    for page in _luma_pages():
        found.extend(_scrape_luma_page(page, interests, cutoff))
    return found


def search_london_events(days_ahead: int = 60) -> list[dict]:
    raw_interests = os.getenv(
        "EVENT_INTERESTS",
        "fintech,startup,founder,design,technology,Black in tech,networking,AI,art,creative"
    )
    interests = [i.strip() for i in raw_interests.split(",")]

    events = _meetup_events(interests, days_ahead)
    events += _luma_events(interests, days_ahead)

    # Deduplicate by name
    seen = set()
    unique = []
    for e in events:
        if e["name"] not in seen:
            seen.add(e["name"])
            unique.append(e)

    return unique[:8]


def format_event_suggestions(events: list[dict]) -> str:
    if not events:
        return "_No matching London events found this week — check Luma and Meetup manually._"
    lines = []
    for e in events:
        lines.append(f"• *{e['name']}* — {e['date']}\n  {e['link']}")
    return "\n".join(lines)
