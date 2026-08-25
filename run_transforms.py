"""
MoonRidge — run_transforms.py
Calls the 9 nightly SQL transform stored procedures via supabase.rpc().
Turns the raw_* staging tables that extract_load.py fills into clean
fact_* tables.

To be run after extract_load.py:

SCOPE: this script only handles the transforms whose raw data is loaded
by the nightly extract_load.py run. Tables that need to stay fresh during
the day (market movers, news, overview, market status) are transformed by
their own cycle scripts instead -- see the note above the TRANSFORMS list.

DEPENDENCY ORDER: these 9 transforms are independent of each other -- each
reads only from its own raw_* table. Order here is for readable logs, not
correctness.
"""

import os
import time
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, ClientOptions

from pipeline_logger import setup_logging, RunStats

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
    options=ClientOptions(postgrest_client_timeout=300)
)

log, log_file = setup_logging("run_transforms")
stats = RunStats()

# Ordered list: each entry is (function_name, display_label).
#
# NOT in this list -- these tables are kept fresh by their own scripts,
# because a nightly transform would leave them stale all day:
#   fact_market_movers  -- transform chained in cycle_market_movers.py
#                          after each raw load (every 2 min, market hours)
#   fact_news           -- transform chained in cycle_news_overview.py
#                          at the end of each lap
#   fact_overview       -- transform chained in cycle_news_overview.py
#                          at the end of each market-hours lap
#   fact_market_status  -- no transform at all; cycle_market_status.py
#                          writes to the fact table directly (ETL)
#   fact_daily_price    -- no transform; load_daily_price.py writes direct
#   fact_upcoming_ipos  -- no transform; load_ipo_calendar.py writes direct
#   fact_index_data     -- transform chained in load_index_data.py
TRANSFORMS = [
    ("transform_income",                  "fact_income"),
    ("transform_balance_sheet",           "fact_balance_sheet"),
    ("transform_cash_flow",               "fact_cash_flow"),
    ("transform_earnings",                "fact_earnings"),
    ("transform_earnings_calendar",       "fact_earnings_calendar"),
    ("transform_dividends",               "fact_dividends"),
    ("transform_splits",                  "fact_splits"),
    ("transform_insider_transactions",    "fact_insider_transactions"),
    ("transform_institutional_holdings",  "fact_institutional_holdings"),
]


def run_transform(func_name, label):
    """Calls one stored procedure via supabase.rpc(). Returns True on
    success, False on error (logged, doesn't crash the run)."""
    start = time.time()
    try:
        supabase.rpc(func_name).execute()
        elapsed = time.time() - start
        log.info(f"  {label:<40} {elapsed:5.1f}s")
        stats.processed += 1
        return True
    except Exception as e:
        elapsed = time.time() - start
        log.error(f"  {label:<40} FAILED ({elapsed:.1f}s): {e}")
        stats.errors += 1
        return False


def main():
    log.info("=== MoonRidge Transform Run ===")
    log.info(f"Log file: {log_file}")
    log.info(f"Running {len(TRANSFORMS)} transforms\n")

    for func_name, label in TRANSFORMS:
        run_transform(func_name, label)

    log.info(f"\n--- TRANSFORM SUMMARY ---")
    log.info(f"Succeeded: {stats.processed}/{len(TRANSFORMS)} | "
             f"Failed: {stats.errors}/{len(TRANSFORMS)} | "
             f"Elapsed: {(datetime.now() - stats.start_time).total_seconds():.1f}s")

    if stats.errors > 0:
        log.warning(f"\n{stats.errors} transform(s) failed — check the log above for details.")


if __name__ == "__main__":
    main()