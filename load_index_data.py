"""
load_index_data.py
Scheduled to run daily at 4:30 PM ET (alongside load_daily_price.py).

Indices tracked:
  SPX  — S&P 500
  DJI  — Dow Jones Industrial Average
  COMP — Nasdaq Composite
  RUT  — Russell 2000
  VIX  — CBOE Volatility Index
  NDX  — Nasdaq 100

"""

import os
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

log, log_file = setup_logging("load_index_data")
stats = RunStats()

SLEEP_SECONDS = 60 / 75

INDICES = [
    ("SPX",  "S&P 500"),
    ("DJI",  "Dow Jones Industrial Average"),
    ("COMP", "Nasdaq Composite"),
    ("RUT",  "Russell 2000"),
    ("VIX",  "CBOE Volatility Index"),
    ("NDX",  "Nasdaq 100"),
]


class RateLimitHit(Exception):
    pass


def check_json_response(data, symbol, label):
    if not isinstance(data, dict):
        return True
    if "Error Message" in data:
        log.warning(f"  {symbol} / {label} -- Error Message: {data['Error Message']}")
        stats.warnings += 1
        return False
    if "message" in data and len(data) == 1:
        log.warning(f"  {symbol} / {label} -- message: {data['message']}")
        stats.warnings += 1
        return False
    if "Information" in data or "Note" in data:
        message = data.get("Information") or data.get("Note")
        raise RateLimitHit(f"{symbol} / {label}: {message}")
    return True


def load_index(symbol, display_name):
    response = requests.get(BASE_URL, params={
        "function": "INDEX_DATA",
        "symbol": symbol,
        "interval": "daily",
        "apikey": API_KEY
    })
    stats.api_calls += 1
    time.sleep(SLEEP_SECONDS)

    try:
        data = response.json()
    except ValueError:
        log.warning(f"  {symbol} / INDEX_DATA did not return valid JSON")
        stats.warnings += 1
        return

    if not check_json_response(data, symbol, "INDEX_DATA"):
        return

    if "data" not in data or not data["data"]:
        log.warning(f"  {symbol} — no 'data' array in response")
        stats.warnings += 1
        return

    supabase.table("raw_index_data").upsert({
        "symbol": symbol,
        "raw_json": data,
        "loaded_at": datetime.now().isoformat()
    }, on_conflict="symbol").execute()

    log.info(f"  {symbol:<6} ({display_name}) — {len(data['data'])} daily rows in raw")
    stats.processed += 1


def main():
    log.info("=== MoonRidge Index Data Load ===")
    log.info(f"Log file: {log_file}\n")

    try:
        for symbol, display_name in INDICES:
            load_index(symbol, display_name)

    except RateLimitHit as e:
        log.error(f"\nSTOPPED: {e}")
        log.info(f"\n--- RUN SUMMARY (interrupted) ---")
        log.info(stats.summary())
        return

    
    log.info("\nRunning transform_index_data()...")
    try:
        supabase.rpc("transform_index_data").execute()
        log.info("  Transform complete.")
    except Exception as e:
        log.error(f"  Transform failed: {e}")
        stats.errors += 1

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()