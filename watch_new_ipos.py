"""
watch_new_ipos.py
Task Scheduler fires this every 5 minutes during market hours.

Checks each ticker queued by load_ipo_calendar.py (via pending_ipos.json)
to see if Alpha Vantage now has real OVERVIEW data for it. Once confirmed,
runs a full first-time load and removes it from the watch list.

Checks each ticker queued by load_ipo_calendar.py (via pending_ipos.json)
to see if Alpha Vantage now has real OVERVIEW data for it. Once confirmed,
loads the overview and removes it from the watch list.

OVERVIEW ONLY. Nothing else is worth calling on day 1 
Fully standalone (except the shared pipeline_logger).
"""

import json
import os
import time
from datetime import date, datetime

import requests
from dotenv import load_dotenv
from supabase import create_client

from pipeline_logger import setup_logging, RunStats

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"

log, log_file = setup_logging("watch_new_ipos")
stats = RunStats()

SLEEP_SECONDS = 60 / 75
PENDING_FILE = "pending_ipos.json"
GIVE_UP_AFTER_DAYS = 5


class RateLimitHit(Exception):
    pass


def check_json_response(data, ticker, label):
    if not isinstance(data, dict):
        return True
    if "Error Message" in data:
        log.warning(f"  {ticker} / {label} -- Error Message: {data['Error Message']}")
        stats.warnings += 1
        return False
    if "message" in data and len(data) == 1:
        log.warning(f"  {ticker} / {label} -- message: {data['message']}")
        stats.warnings += 1
        return False
    if "Information" in data or "Note" in data:
        message = data.get("Information") or data.get("Note")
        raise RateLimitHit(f"{ticker} / {label}: {message}")
    return True


def call_av(params, label, ticker=""):
    response = requests.get(BASE_URL, params={**params, "apikey": API_KEY})
    stats.api_calls += 1
    time.sleep(SLEEP_SECONDS)
    return response


def extract_json(function, ticker, extra_params=None):
    params = {"function": function, "symbol": ticker, **(extra_params or {})}
    response = call_av(params, function, ticker)
    try:
        return response.json()
    except ValueError:
        log.warning(f"  {ticker} / {function} did not return valid JSON")
        stats.warnings += 1
        return {}


def load_json(table, ticker, data, label):
    if not check_json_response(data, ticker, label):
        return False
    supabase.table(table).upsert({
        "ticker": ticker,
        "raw_json": data,
        "loaded_at": datetime.now().isoformat()
    }, on_conflict="ticker").execute()
    log.debug(f"  Loaded {ticker} into {table}")
    return True


def first_load(ticker, overview_data):
    
    log.info(f"  {ticker}: now live -- loading overview")
    load_json("raw_company_overview", ticker, overview_data, "OVERVIEW")
    stats.processed += 1


def load_pending():
    if not os.path.exists(PENDING_FILE):
        return []
    with open(PENDING_FILE) as f:
        return json.load(f)


def save_pending(pending):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)


def main():
    pending = load_pending()
    if not pending:
        return

    log.info(f"=== Watching {len(pending)} pending IPO ticker(s) ===")
    log.info(f"Log file: {log_file}")
    today = date.today()
    resolved_tickers = set()

    try:
        for entry in pending:
            ticker = entry["ticker"]
            added_at = date.fromisoformat(entry["added_at"])

            if (today - added_at).days > GIVE_UP_AFTER_DAYS:
                log.warning(f"  {ticker}: no data after {GIVE_UP_AFTER_DAYS} days -- giving up")
                stats.warnings += 1
                resolved_tickers.add(ticker)
                continue

            data = extract_json("OVERVIEW", ticker)
            if not data.get("Symbol"):
                log.info(f"  {ticker}: not live yet")
                continue

            first_load(ticker, data)
            resolved_tickers.add(ticker)

    except RateLimitHit as e:
        log.error(f"STOPPED: {e}")

    still_pending = [p for p in pending if p["ticker"] not in resolved_tickers]
    save_pending(still_pending)

    if still_pending:
        log.info(f"  Still waiting on: {[p['ticker'] for p in still_pending]}")
    else:
        log.info("  All caught up")

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()