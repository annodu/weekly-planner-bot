"""
Run once to authenticate with Google Calendar.
Produces token.pickle which the bot reuses.
"""
from dotenv import load_dotenv
load_dotenv()
import calendar_client

service = calendar_client.get_calendar_service()
print("✅ Google Calendar authenticated successfully.")
print("   token.pickle saved — you won't need to run this again unless it expires.")
