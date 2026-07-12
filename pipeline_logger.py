"""
pipeline_logger.py
Shared module imported by all pipeline scripts.

Provides:
  setup_logging(script_name) — creates a logger that writes to BOTH the
    console and a timestamped log file in the logs/ folder (so you can review past runs).

  RunStats — simple counter object for tracking processed/skipped/warned/
    errored tickers, producing a summary line at the end of each run.
"""

import logging
import os
from datetime import datetime


def setup_logging(script_name):
    """
    Returns (logger, log_file_path).

    Console output stays clean (just the message, no timestamps). The log file gets the full
    detail: timestamp, level, message.
    """
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = f"logs/{script_name}_{timestamp}.log"

    logger = logging.getLogger(script_name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if setup_logging is called more than once
    if logger.handlers:
        logger.handlers.clear()

    # File handler — captures everything (DEBUG and above)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler — INFO and above, clean format (no timestamp clutter)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger, log_file


class RunStats:
    """
    Tracks counts throughout a pipeline run. Each script increments the
    counters relevant to it; at the end, .summary() returns a single
    line capturing the whole run's outcome.
    """

    def __init__(self):
        self.processed = 0
        self.skipped_cadence = 0
        self.skipped_checkpoint = 0
        self.warnings = 0
        self.errors = 0
        self.skip_list_adds = 0
        self.api_calls = 0
        self.start_time = datetime.now()

    def summary(self):
        elapsed = datetime.now() - self.start_time
        minutes = elapsed.total_seconds() / 60
        parts = [
            f"Processed: {self.processed}",
            f"Skipped (cadence): {self.skipped_cadence}",
            f"Skipped (checkpoint): {self.skipped_checkpoint}",
            f"Warnings: {self.warnings}",
            f"Errors: {self.errors}",
            f"Skip list: {self.skip_list_adds}",
            f"API calls: {self.api_calls}",
            f"Elapsed: {minutes:.1f} min",
        ]
        return " | ".join(parts)