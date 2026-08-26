"""
cycle_news_overview.py
Runs continuously, updating news all time. 

Sweeps through all active tickers: news every lap (always), overview only
while the market is open. Use --force to override market-hours check.

"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from supabase import create_client

from pipeline_logger import setup_logging, RunStats

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"

log, log_file = setup_logging("cycle_news_overview")
stats = RunStats()

RATE_LIMIT_PER_MINUTE = 75
SLEEP_SECONDS = 60 / RATE_LIMIT_PER_MINUTE

TEST_TICKER_LIMIT = None
NEWS_LIMIT = "10"

FORCE_MODE = "--force" in sys.argv

from market_hours import is_market_open


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


def load_overview(ticker):
    params = {"function": "OVERVIEW", "symbol": ticker}
    response = call_av(params, "OVERVIEW", ticker)
    try:
        data = response.json()
    except ValueError:
        log.warning(f"  {ticker} / OVERVIEW did not return valid JSON")
        stats.warnings += 1
        return
    if not check_json_response(data, ticker, "OVERVIEW"):
        return
    supabase.table("raw_company_overview").upsert({
        "ticker": ticker,
        "raw_json": data,
        "loaded_at": datetime.now().isoformat()
    }, on_conflict="ticker").execute()


def load_news(ticker):
    time_from = (datetime.now() - timedelta(days=7)).strftime("%Y%m%dT0000")
    response = call_av(
        {"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": NEWS_LIMIT, "time_from": time_from},
        "NEWS_SENTIMENT", ticker
    )

    try:
        data = response.json()
    except ValueError:
        log.warning(f"  {ticker} / NEWS_SENTIMENT did not return valid JSON")
        stats.warnings += 1
        return
    if not check_json_response(data, ticker, "NEWS_SENTIMENT"):
        return
    supabase.table("raw_news").upsert({
        "ticker": ticker,
        "raw_json": data,
        "loaded_at": datetime.now().isoformat()
    }, on_conflict="ticker").execute()


def main():
    log.info("=== MoonRidge News & Overview Cycle ===")
    log.info(f"Log file: {log_file}")
    if FORCE_MODE:
        log.info("** FORCE MODE -- overview fires regardless of market hours **")
    log.info("Press Ctrl+C to stop.\n")

    lap = 0

    try:
        while True:
            lap += 1
            tickers = get_active_tickers()
            if TEST_TICKER_LIMIT is not None:
                tickers = tickers[:TEST_TICKER_LIMIT]

            market_open = FORCE_MODE or is_market_open()
            mode = "news + overview" if market_open else "news only"
            log.info(f"\n--- Lap {lap}: {len(tickers)} ticker(s), starting mode: {mode} ---")

            overview_loaded_this_lap = False

            for idx, ticker in enumerate(tickers, start=1):
                market_open = FORCE_MODE or is_market_open()

                try:
                    load_news(ticker)
                    if market_open:
                        load_overview(ticker)
                        overview_loaded_this_lap = True
                    stats.processed += 1
                except RateLimitHit:
                    raise
                except Exception as e:
                    log.error(f"  ERROR processing {ticker}: {e}")
                    stats.errors += 1
                    continue

                if idx % 200 == 0:
                    mode = "news + overview" if market_open else "news only"
                    log.info(f"  ... {idx}/{len(tickers)} tickers processed this lap ({mode})")

            log.info(f"  Lap {lap} complete ({len(tickers)} tickers)")

            
            try:
                supabase.rpc("transform_news").execute()
                log.debug("  Transformed -> fact_news")
            except Exception as e:
                log.error(f"  transform_news failed: {e}")
                stats.errors += 1

            if overview_loaded_this_lap:
                try:
                    supabase.rpc("transform_overview").execute()
                    log.debug("  Transformed -> fact_overview")
                except Exception as e:
                    log.error(f"  transform_overview failed: {e}")
                    stats.errors += 1

    except RateLimitHit as e:
        log.error(f"\nSTOPPED: {e}")
    except KeyboardInterrupt:
        log.info("\nStopped by user.")

    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())


if __name__ == "__main__":
    main()