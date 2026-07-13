"""
cycle_market_movers.py

Scheduled to start at market opening and loops till market close

Refreshes raw_market_movers (TOP_GAINERS_LOSERS_ACTIVE) every 2 minutes while
the market is open. Use --force to override market-hours check.
"""
import json
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from supabase import create_client

from pipeline_logger import setup_logging, RunStats

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"

log, log_file = setup_logging("cycle_market_movers")
stats = RunStats()

SLEEP_SECONDS = 60 / 75
CYCLE_INTERVAL = 120
IDLE_INTERVAL = 60

FORCE_MODE = "--force" in sys.argv

from market_hours import is_market_open


class RateLimitHit(Exception):
    pass


def check_json_response(data, label):
    if not isinstance(data, dict):
        return True
    if "Error Message" in data:
        log.warning(f"  {label} -- Error Message: {data['Error Message']}")
        stats.warnings += 1
        return False
    if "message" in data and len(data) == 1:
        log.warning(f"  {label} -- message: {data['message']}")
        stats.warnings += 1
        return False
    if "Information" in data or "Note" in data:
        message = data.get("Information") or data.get("Note")
        raise RateLimitHit(f"{label}: {message}")
    return True


def load_market_movers():
    response = requests.get(BASE_URL, params={
        "function": "TOP_GAINERS_LOSERS",
        "apikey": API_KEY
    })
    stats.api_calls += 1
    time.sleep(SLEEP_SECONDS)

    try:
        data = response.json()
    except ValueError:
        log.warning("  TOP_GAINERS_LOSERS did not return valid JSON")
        stats.warnings += 1
        return

    if not check_json_response(data, "TOP_GAINERS_LOSERS"):
        return

    result = supabase.table("raw_market_movers").update({
        "raw_json": data,
        "loaded_at": datetime.now().isoformat()
    }).eq("id", 1).execute()

    if not result.data:
        log.error("  raw_market_movers has no row with id=1 -- seed it first")
        stats.errors += 1
        return

    log.info(f"  [{datetime.now().strftime('%H:%M:%S')}] Loaded -> raw_market_movers")
    stats.processed += 1

    # Transform immediately so fact_market_movers stays fresh all day.
    
    try:
        supabase.rpc("transform_market_movers").execute()
        log.debug("  Transformed -> fact_market_movers")
    except Exception as e:
        log.error(f"  Transform failed: {e}")
        stats.errors += 1


def main():
    log.info("=== MoonRidge Market Movers Cycle ===")
    log.info(f"Log file: {log_file}")
    if FORCE_MODE:
        log.info("** FORCE MODE -- ignoring market hours **")
    log.info("Press Ctrl+C to stop.\n")

    try:
        while True:
            if FORCE_MODE or is_market_open():
                load_market_movers()
                time.sleep(CYCLE_INTERVAL)
            else:
                log.debug(f"  [{datetime.now().strftime('%H:%M:%S')}] Market closed -- idling")
                time.sleep(IDLE_INTERVAL)

    except RateLimitHit as e:
        log.error(f"\nSTOPPED: {e}")
    except KeyboardInterrupt:
        log.info("\nStopped by user.")

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()