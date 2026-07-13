"""
load_ipo_calendar.py
Scheduled to run once daily, evening (alongside extract_load.py).

1. Calls IPO_CALENDAR
2. Parses CSV → truncate+reload fact_upcoming_ipos
3. Finds qualifying tickers IPOing tomorrow → adds them to dim_tickers
   and queues them in pending_ipos.json for watch_new_ipos.py
"""

import csv
import io
import json
import os
import time
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv
from supabase import create_client

from pipeline_logger import setup_logging, RunStats

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"

log, log_file = setup_logging("load_ipo_calendar")
stats = RunStats()

SLEEP_SECONDS = 60 / 75
PENDING_FILE = "pending_ipos.json"
APPROVED_EXCHANGES = {"NYSE", "NASDAQ", "NYSE ARCA", "BATS"}


class RateLimitHit(Exception):
    pass


def check_csv_response(text, label):
    stripped = text.strip()
    if not stripped.startswith("{"):
        return True
    try:
        as_json = json.loads(stripped)
    except ValueError:
        log.warning(f"  {label} returned an unexpected response: {stripped[:200]}")
        stats.warnings += 1
        return False
    if "Information" in as_json or "Note" in as_json:
        message = as_json.get("Information") or as_json.get("Note")
        raise RateLimitHit(f"{label}: {message}")
    if "Error Message" in as_json:
        log.warning(f"  {label} -- Error Message: {as_json['Error Message']}")
        stats.warnings += 1
        return False
    return True


def load_pending():
    if not os.path.exists(PENDING_FILE):
        return []
    with open(PENDING_FILE) as f:
        return json.load(f)


def save_pending(pending):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)


def ticker_qualifies(symbol, exchange):
    if exchange not in APPROVED_EXCHANGES:
        return False
    if len(symbol) > 5 or "." in symbol or "-" in symbol:
        return False
    if symbol.endswith(("W", "R", "U")):
        return False
    return True


def main():
    log.info("=== MoonRidge IPO Calendar Load ===")
    log.info(f"Log file: {log_file}\n")
    tomorrow = date.today() + timedelta(days=1)

    try:
        response = requests.get(BASE_URL, params={
            "function": "IPO_CALENDAR",
            "apikey": API_KEY
        })
        stats.api_calls += 1
        time.sleep(SLEEP_SECONDS)
    except Exception as e:
        log.error(f"API call failed: {e}")
        stats.errors += 1
        return

    if not check_csv_response(response.text, "IPO_CALENDAR"):
        return

    # No raw table. The CSV is parsed straight from response.text below,
    
    reader = csv.DictReader(io.StringIO(response.text))
    all_rows = []

    for row in reader:
        try:
            all_rows.append({
                "ticker": row["symbol"].strip(),
                "name": row["name"].strip(),
                "ipo_date": row["ipoDate"].strip(),
                "price_range_low": float(row["priceRangeLow"]) if row["priceRangeLow"] else 0,
                "price_range_high": float(row["priceRangeHigh"]) if row["priceRangeHigh"] else 0,
                "currency": row["currency"].strip(),
                "exchange": row["exchange"].strip(),
                "updated_at": datetime.now().isoformat()
            })
        except (KeyError, ValueError) as e:
            log.debug(f"  Skipped malformed IPO row: {e}")
            continue

    supabase.table("fact_upcoming_ipos").delete().neq("ticker", "").execute()
    if all_rows:
        batch_size = 500
        for i in range(0, len(all_rows), batch_size):
            batch = all_rows[i:i + batch_size]
            supabase.table("fact_upcoming_ipos").insert(batch).execute()
    log.info(f"  Loaded {len(all_rows)} rows -> fact_upcoming_ipos")
    stats.processed = len(all_rows)

    pending = load_pending()
    already_pending = {p["ticker"] for p in pending}
    new_watch = []

    for row in all_rows:
        try:
            ipo_date = date.fromisoformat(row["ipo_date"])
        except ValueError:
            continue

        if ipo_date != tomorrow:
            continue
        if not ticker_qualifies(row["ticker"], row["exchange"]):
            continue
        if row["ticker"] in already_pending:
            continue

        new_watch.append(row)

    if new_watch:
        dim_rows = [{
            "ticker": r["ticker"],
            "name": r["name"],
            "exchange": r["exchange"],
            "asset_type": "Stock",
            "ipo_date": r["ipo_date"],
            "status": "Active"
        } for r in new_watch]
        supabase.table("dim_tickers").upsert(
            dim_rows, on_conflict="ticker", ignore_duplicates=True
        ).execute()

        for r in new_watch:
            pending.append({
                "ticker": r["ticker"],
                "added_at": date.today().isoformat()
            })
        save_pending(pending)

        log.info(f"  Queued {len(new_watch)} ticker(s) for tomorrow's watch:")
        for r in new_watch:
            log.info(f"    {r['ticker']} ({r['name']}) -- IPO {r['ipo_date']}")
    else:
        log.info(f"  No qualifying IPOs found for {tomorrow}")

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()