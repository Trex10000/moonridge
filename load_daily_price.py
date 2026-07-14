"""
load_daily_price.py
Task Scheduler fires this once daily at 4:30 PM ET (after market close).
Sweeps all active tickers, loading compact daily price data. Runs once
and exits.

[This can be replaced with a real time daily price option with a premium api tier when switching to commercial usage. 
And loop in between market hours for real time price or use websocket]

Fully standalone — no imports from extract_load.py or other project files
(except the shared pipeline_logger).

CHECKPOINT: completed tickers are written to daily_price_checkpoint.txt
after each successful load. If the run is interrupted, re-running picks
up from where it left off. The checkpoint is cleared automatically at the
end of a successful full run. 
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

log, log_file = setup_logging("load_daily_price")
stats = RunStats()

RATE_LIMIT_PER_MINUTE = 75
SLEEP_SECONDS = 60 / RATE_LIMIT_PER_MINUTE

TEST_TICKER_LIMIT = None

CHECKPOINT_FILE = "daily_price_checkpoint.txt"


class RateLimitHit(Exception):
    pass


# --- CHECKPOINT ---

def load_completed_tickers():
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE) as f:
        return set(line.strip() for line in f if line.strip())


def mark_completed(ticker):
    with open(CHECKPOINT_FILE, "a") as f:
        f.write(ticker + "\n")


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


# --- RESPONSE VALIDATION ---

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


# --- API CALL ---

def call_av(params, label, ticker=""):
    response = requests.get(BASE_URL, params={**params, "apikey": API_KEY})
    stats.api_calls += 1
    if stats.api_calls % 200 == 0:
        log.info(f"  ... {stats.api_calls} calls made so far")
    time.sleep(SLEEP_SECONDS)
    return response


# --- TICKERS ---

def get_active_tickers():
    page_size = 1000
    all_tickers = []
    start = 0
    while True:
        result = supabase.table("dim_tickers") \
            .select("ticker") \
            .eq("status", "Active") \
            .order("ticker") \
            .range(start, start + page_size - 1) \
            .execute()
        if not result.data:
            break
        all_tickers.extend(row["ticker"] for row in result.data)
        if len(result.data) < page_size:
            break
        start += page_size
    return all_tickers


# --- PRICE LOAD ---

def needs_full_price_history(ticker):
    result = supabase.table("fact_daily_price") \
        .select("ticker") \
        .eq("ticker", ticker) \
        .limit(1) \
        .execute()
    return not result.data


def load_daily_price(ticker):
    outputsize = "full" if needs_full_price_history(ticker) else "compact"
    response = call_av(
        {"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": ticker, "outputsize": outputsize},
        "TIME_SERIES_DAILY_ADJUSTED", ticker
    )

    try:
        data = response.json()
    except ValueError:
        log.warning(f"  {ticker} / TIME_SERIES_DAILY_ADJUSTED did not return valid JSON")
        stats.warnings += 1
        return

    if not check_json_response(data, ticker, "TIME_SERIES_DAILY_ADJUSTED"):
        return

    time_series = data.get("Time Series (Daily)")
    if not time_series:
        log.warning(f"  No daily price data for {ticker}")
        stats.warnings += 1
        return

    rows = []
    for date_str, values in time_series.items():
        rows.append({
            "ticker": ticker,
            "price_date": date_str,
            "open": float(values["1. open"]),
            "high": float(values["2. high"]),
            "low": float(values["3. low"]),
            "close": float(values["4. close"]),
            "adjusted_close": float(values["5. adjusted close"]),
            "volume": int(values["6. volume"]),
            "dividend_amount": float(values["7. dividend amount"]),
            "split_coefficient": float(values["8. split coefficient"])
        })

    batch_size = 500
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]
        supabase.table("fact_daily_price").upsert(
            batch, on_conflict="ticker,price_date"
        ).execute()
    log.debug(f"  Loaded {total} price row(s) for {ticker} ({outputsize})")
    stats.processed += 1


# --- MAIN ---

def main():
    log.info("=== MoonRidge Daily Price Load ===")
    log.info(f"Log file: {log_file}")
    log.info(f"Config: TEST_TICKER_LIMIT={TEST_TICKER_LIMIT}\n")

    completed = load_completed_tickers()
    if completed:
        log.warning(f"Found {CHECKPOINT_FILE} with {len(completed)} ticker(s) already done.")
        log.warning("Resuming from where the last run stopped.\n")

    try:
        tickers = get_active_tickers()
        log.info(f"Found {len(tickers)} active stocks")

        if TEST_TICKER_LIMIT is not None:
            tickers = tickers[:TEST_TICKER_LIMIT]
        log.info(f"Processing {len(tickers)} ticker(s)\n")

        for idx, ticker in enumerate(tickers, start=1):
            if ticker in completed:
                log.info(f"[{idx}/{len(tickers)}] Skipping {ticker} (already done)")
                stats.skipped_checkpoint += 1
                continue

            log.info(f"[{idx}/{len(tickers)}] {ticker}...")
            try:
                load_daily_price(ticker)
                mark_completed(ticker)
            except RateLimitHit:
                raise
            except Exception as e:
                log.error(f"  ERROR processing {ticker}: {e}")
                stats.errors += 1
                continue

    except RateLimitHit as e:
        log.error(f"\nSTOPPED: Rate limit hit — {e}")
        log.error(f"Re-run the script to resume from where it stopped.")

    else:
        clear_checkpoint()
        log.info("Checkpoint cleared — full run completed successfully.")

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()