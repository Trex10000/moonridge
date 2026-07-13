"""
MoonRidge — market_hours.py
Shared module imported by cycle_market_movers.py and cycle_news_overview.py.

Provides is_market_open(): checks the MARKET_STATUS API every 30 minutes
between 9:31 AM and 4:31 PM ET, caches the result in between calls, and
writes each fresh status to fact_market_status so the frontend always has
a live open/closed indicator.

Once the market has been seen "open" and then comes back "closed", the
status stays "closed" for the rest of the day (no more API calls needed).

On days outside the polling window (weekends, holidays where the cycle
scripts aren't running), no calls are made and is_market_open() returns
False based on the clock alone.

"""

import logging
import os
import time
from datetime import datetime, time as dtime

import requests
from dotenv import load_dotenv
from supabase import create_client

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

load_dotenv()

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"
SLEEP_SECONDS = 60 / 75

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

EASTERN = ZoneInfo("America/New_York")
WINDOW_START = dtime(9, 31)    # 9:31 AM ET
WINDOW_END = dtime(16, 31)     # 4:31 PM ET
POLL_INTERVAL = 30 * 60        # 30 minutes in seconds

TARGET_REGION = "United States"
TARGET_TYPE = "Equity"

log = logging.getLogger("market_hours")

_cache = {
    "date": None,           # which day this cache is for
    "is_open": False,       # last known status
    "seen_open": False,     # have we seen "open" today?
    "closed_after_open": False,  # seen "closed" AFTER "open"? -> done for the day
    "last_api_call": 0.0,   # time.time() of the last API call
}


def _now_et():
    return datetime.now(EASTERN)


def _in_window():
    return WINDOW_START <= _now_et().time() <= WINDOW_END


def _reset_if_new_day():
    today = _now_et().date()
    if _cache["date"] != today:
        _cache.update({
            "date": today,
            "is_open": False,
            "seen_open": False,
            "closed_after_open": False,
            "last_api_call": 0.0,
        })


def _write_to_fact(market_row):
    """TRUNCATE + INSERT into fact_market_status. Snapshot semantics."""
    try:
        supabase.table("fact_market_status").delete().neq("region", "").execute()
        supabase.table("fact_market_status").insert({
            "region": market_row.get("region"),
            "market_type": market_row.get("market_type"),
            "primary_exchanges": market_row.get("primary_exchanges"),
            "local_open": market_row.get("local_open"),
            "local_close": market_row.get("local_close"),
            "current_status": market_row.get("current_status"),
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        log.warning(f"  Failed to write fact_market_status: {e}")


def _check_market_status_api():
    """Calls MARKET_STATUS, writes to fact_market_status, returns True if open."""
    try:
        response = requests.get(BASE_URL, params={
            "function": "MARKET_STATUS",
            "apikey": API_KEY
        })
        time.sleep(SLEEP_SECONDS)
        data = response.json()

        for market in data.get("markets", []):
            if (market.get("region") == TARGET_REGION
                    and market.get("market_type") == TARGET_TYPE):
                status = (market.get("current_status") or "").strip().lower()
                is_open = status == "open"
                log.info(f"  MARKET_STATUS API: US Equity = {status}")

                # Write to fact_market_status so the frontend has live data
                _write_to_fact(market)

                return is_open

        log.warning("  US Equity market not found in MARKET_STATUS response")
        return False

    except Exception as e:
        log.warning(f"  MARKET_STATUS call failed ({e}) -- assuming closed")
        return False


def is_market_open():
    """Returns True if the US equity market is currently open.

    Calls the API at most once every 30 minutes during the 9:31 AM to 4:31 PM
    ET window. Writes status to fact_market_status on every API call. Caches
    the result in between. Once "closed" is seen after "open", stays closed
    for the rest of the day with no further API calls.

    Outside the window, returns False immediately (no API call).
    """
    _reset_if_new_day()

    # Outside the polling window — definitely closed
    if not _in_window():
        return False

    # Already confirmed closed after being open today — done
    if _cache["closed_after_open"]:
        return False

    # Check if 30 minutes have passed since the last API call
    now = time.time()
    if now - _cache["last_api_call"] < POLL_INTERVAL:
        return _cache["is_open"]

    # Time for a fresh API call
    _cache["last_api_call"] = now
    is_open = _check_market_status_api()
    _cache["is_open"] = is_open

    if is_open:
        _cache["seen_open"] = True
    elif _cache["seen_open"]:
        # Was open, now closed — market closed for the day
        _cache["closed_after_open"] = True
        log.info("  Market closed after being open — no more API calls today")

    return is_open