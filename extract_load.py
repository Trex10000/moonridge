"""
extract_load.py
Nightly trigger. (API - 75 req/min -- for testing, will update to a commercial preimum tier if required).

ELT pipeline: pulls raw data from source and loads it into Supabase
staging (raw_*) tables. SQL transforms turn this into the clean fact_* tables that the frontend reads.

LOGGING: all output goes to both the console (so you can watch it live)
AND a timestamped log file in the logs/ folder (so you can review past
runs). Run summary (processed/skipped/warned/errored/API calls/elapsed)
is printed at the end of every run, including interrupted ones.
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

log, log_file = setup_logging("extract_load")
stats = RunStats()

# --- CONFIG ---

RATE_LIMIT_PER_MINUTE = 75
SLEEP_SECONDS = 60 / RATE_LIMIT_PER_MINUTE

MAX_CALLS_PER_RUN = 100_000

TEST_TICKER_LIMIT = 1000

FORCE_FULL_LOAD = True

CHECKPOINT_FILE = "checkpoint_1.txt"


class RateLimitHit(Exception):
    pass


def update_singleton_table(table, payload):
    result = supabase.table(table).update(payload).eq("id", 1).execute()
    if not result.data:
        raise RuntimeError(
            f"{table} has no row with id=1 -- run the one-time seed SQL "
            f"first, then re-run this script."
        )
    log.info(f"  Loaded -> {table}")


# --- CHECKPOINT / RESUMABILITY ---

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


# --- API CALL WRAPPER ---

def call_av(params, label, ticker=""):
    if stats.api_calls >= MAX_CALLS_PER_RUN:
        raise RateLimitHit(f"Reached MAX_CALLS_PER_RUN ({MAX_CALLS_PER_RUN}) before calling {label}")
    response = requests.get(BASE_URL, params={**params, "apikey": API_KEY})
    stats.api_calls += 1
    if stats.api_calls % 200 == 0:
        log.info(f"  ... {stats.api_calls} calls made so far this run")
    time.sleep(SLEEP_SECONDS)
    return response


# --- DIM TICKERS ---

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


def load_listing_status():
    response = call_av({"function": "LISTING_STATUS"}, "LISTING_STATUS")
    if not check_csv_response(response.text, "LISTING_STATUS"):
        return
    update_singleton_table("raw_listing_status", {
        "raw_csv": response.text,
        "loaded_at": datetime.now().isoformat()
    })


def refresh_dim_tickers():
    supabase.rpc("refresh_dim_tickers").execute()
    log.info("  Refreshed -> dim_tickers")


# --- GENERIC PER-TICKER JSON LOAD ---

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


# --- SINGLE-CALL, ALL-TICKER ENDPOINTS ---

def load_earnings_calendar():
    response = call_av({"function": "EARNINGS_CALENDAR", "horizon": "12month"}, "EARNINGS_CALENDAR")
    if not check_csv_response(response.text, "EARNINGS_CALENDAR"):
        return
    update_singleton_table("raw_earnings_calendar", {
        "raw_csv": response.text,
        "loaded_at": datetime.now().isoformat()
    })


# --- FUNDAMENTALS: FISCAL-DATE-AWARE CHECKPOINT SCHEDULES ---

def build_checkpoint_schedule(early_points, fine_start, fine_end, fine_step, tail_step, tail_end):
    checkpoints = set(early_points)
    checkpoints.update(range(fine_start, fine_end + 1, fine_step))
    checkpoints.update(range(fine_end + tail_step, tail_end + 1, tail_step))
    return checkpoints


QUARTERLY_CHECKPOINTS = build_checkpoint_schedule(
    early_points=[20, 25, 30],
    fine_start=30, fine_end=46, fine_step=2,
    tail_step=5, tail_end=120
)

ANNUAL_CHECKPOINTS = build_checkpoint_schedule(
    early_points=[40, 50, 60],
    fine_start=60, fine_end=92, fine_step=4,
    tail_step=10, tail_end=240
)


def days_since_fiscal_date(table, ticker, period):
    result = supabase.table(table) \
        .select("fiscal_date") \
        .eq("ticker", ticker) \
        .eq("period", period) \
        .order("fiscal_date", desc=True) \
        .limit(1) \
        .execute()
    if not result.data:
        return None
    fiscal_date = date.fromisoformat(result.data[0]["fiscal_date"])
    return (date.today() - fiscal_date).days


def needs_fundamental_update(ticker):
    quarterly_days = days_since_fiscal_date("fact_income", ticker, "quarterly")
    annual_days = days_since_fiscal_date("fact_income", ticker, "annual")

    if quarterly_days is None and annual_days is None:
        log.debug(f"  {ticker}: No fundamentals data found -> fetching")
        return True

    if quarterly_days is not None and quarterly_days in QUARTERLY_CHECKPOINTS:
        log.debug(f"  {ticker}: Quarterly filing checkpoint (day {quarterly_days}) -> fetching")
        return True

    if annual_days is not None and annual_days in ANNUAL_CHECKPOINTS:
        log.debug(f"  {ticker}: Annual filing checkpoint (day {annual_days}) -> fetching")
        return True

    log.debug(f"  {ticker}: No checkpoint due today "
              f"(quarterly day {quarterly_days}, annual day {annual_days}) -> skipping")
    return False


# --- GENERIC FRESHNESS CHECK FOR SIMPLE TIME-BASED CADENCES ---

def needs_refresh(table, ticker, cadence_days):
    result = supabase.table(table) \
        .select("loaded_at") \
        .eq("ticker", ticker) \
        .limit(1) \
        .execute()
    if not result.data:
        return True
    loaded_at = datetime.fromisoformat(result.data[0]["loaded_at"])
    days_since = (datetime.now() - loaded_at).days
    return days_since >= cadence_days


# --- SKIP LIST ---

def add_to_skip_list(ticker, reason):
    supabase.table("skip_list").upsert({
        "ticker": ticker,
        "reason": reason,
        "detected_at": datetime.now().isoformat()
    }, on_conflict="ticker").execute()
    log.info(f"  Added {ticker} to skip_list: {reason}")
    stats.skip_list_adds += 1


# --- PER-TICKER LOADERS ---

def load_dividends(ticker):
    data = extract_json("DIVIDENDS", ticker)
    load_json("raw_dividends", ticker, data, "DIVIDENDS")


def load_splits(ticker):
    data = extract_json("SPLITS", ticker)
    load_json("raw_splits", ticker, data, "SPLITS")


def load_insider_transactions(ticker):
    data = extract_json("INSIDER_TRANSACTIONS", ticker)
    load_json("raw_insider_transactions", ticker, data, "INSIDER_TRANSACTIONS")


def load_institutional_holdings(ticker):
    data = extract_json("INSTITUTIONAL_HOLDINGS", ticker)
    load_json("raw_institutional_holdings", ticker, data, "INSTITUTIONAL_HOLDINGS")


# --- MAIN ---

def main():
    log.info("=== MoonRidge Pipeline Run ===")
    log.info(f"Log file: {log_file}")
    log.info(f"Config: FORCE_FULL_LOAD={FORCE_FULL_LOAD}, TEST_TICKER_LIMIT={TEST_TICKER_LIMIT}\n")

    completed = load_completed_tickers()
    if completed:
        log.warning(f"Found {CHECKPOINT_FILE} with {len(completed)} ticker(s) already marked done.")
        log.warning("If you're resuming an interrupted run, this is expected -- continuing.")
        log.warning(f"If you expected a fresh run tonight, stop now and delete {CHECKPOINT_FILE} first.\n")

    try:
        log.info("Loading listing status...")
        load_listing_status()

        log.info("Refreshing dim_tickers...")
        refresh_dim_tickers()

        log.info("Fetching active tickers...")
        tickers = get_active_tickers()
        log.info(f"Found {len(tickers)} active stocks")

        log.info("Loading earnings calendar...")
        load_earnings_calendar()

        if TEST_TICKER_LIMIT is not None:
            tickers = tickers[:TEST_TICKER_LIMIT]
        log.info(f"\nProcessing {len(tickers)} ticker(s)")

        for idx, ticker in enumerate(tickers, start=1):
            if ticker in completed:
                log.info(f"\n[{idx}/{len(tickers)}] Skipping {ticker} (already completed this run)")
                stats.skipped_checkpoint += 1
                continue

            log.info(f"\n[{idx}/{len(tickers)}] Processing {ticker}...")

            try:
                # Fiscal-date-aware checkpoints
                if FORCE_FULL_LOAD or needs_fundamental_update(ticker):
                    income_data = extract_json("INCOME_STATEMENT", ticker)
                    income_ok = load_json("raw_income_statement", ticker, income_data, "INCOME_STATEMENT")
                    load_json("raw_balance_sheet", ticker,
                              extract_json("BALANCE_SHEET", ticker), "BALANCE_SHEET")
                    load_json("raw_cash_flow", ticker,
                              extract_json("CASH_FLOW", ticker), "CASH_FLOW")
                    load_json("raw_earnings", ticker,
                              extract_json("EARNINGS", ticker), "EARNINGS")

                    if not income_ok:
                        reason = income_data.get("Error Message") or income_data.get("message") or "Unknown rejection"
                        add_to_skip_list(ticker, reason)
                else:
                    stats.skipped_cadence += 1

                # Every 2 days
                if FORCE_FULL_LOAD or needs_refresh("raw_dividends", ticker, cadence_days=2):
                    load_dividends(ticker)
                if FORCE_FULL_LOAD or needs_refresh("raw_insider_transactions", ticker, cadence_days=2):
                    load_insider_transactions(ticker)

                # Monthly
                if FORCE_FULL_LOAD or needs_refresh("raw_splits", ticker, cadence_days=30):
                    load_splits(ticker)
                if FORCE_FULL_LOAD or needs_refresh("raw_institutional_holdings", ticker, cadence_days=30):
                    load_institutional_holdings(ticker)

                stats.processed += 1
                mark_completed(ticker)

            except RateLimitHit:
                raise  # let the outer handler catch this
            except Exception as e:
                log.error(f"  ERROR processing {ticker}: {e}")
                stats.errors += 1
                # Don't mark_completed — this ticker will be retried on next run
                continue

    except RateLimitHit as e:
        log.error(f"\nSTOPPED: Alpha Vantage rate limit reached.")
        log.error(f"  {e}")
        log.error(f"  {CHECKPOINT_FILE} preserved -- re-run to resume from where this stopped.")
        log.info(f"\n--- RUN SUMMARY (interrupted) ---")
        log.info(stats.summary())
        return

    clear_checkpoint()
    log.info(f"\n--- RUN SUMMARY ---")
    log.info(stats.summary())
    log.info("Check Supabase to verify all tables.")


if __name__ == "__main__":
    main()