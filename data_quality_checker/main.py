#!/usr/bin/env python3
"""
Data Quality Checker – entry point.

Usage:
    python main.py [--config path/to/config.yaml]

Environment variables (or .env file):
    GOOGLE_APPLICATION_CREDENTIALS  – path to GCP service-account JSON
    EMAIL_PASSWORD                  – SMTP password / app password
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google.cloud import bigquery
from tabulate import tabulate

from src.alerter import send_alert
from src.checker import DataQualityChecker, TableConfig

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config/config.example.yaml → config/config.yaml and edit it."
        )
    with open(path) as f:
        return yaml.safe_load(f)


def parse_tables(raw_tables: list[dict]) -> list[TableConfig]:
    tables = []
    for t in raw_tables:
        tables.append(
            TableConfig(
                name=t["name"],
                source=t["source"],
                target=t["target"],
                primary_keys=t.get("primary_keys", []),
                critical_columns=t.get("critical_columns", []),
                null_threshold_pct=float(t.get("null_threshold_pct", 0.0)),
            )
        )
    return tables


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="BigQuery Data Quality Checker")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file (default: config/config.yaml)",
    )
    args = parser.parse_args()

    # Load secrets from .env if present
    load_dotenv()

    cfg = load_config(Path(args.config))
    setup_logging(
        level=cfg.get("log_level", "INFO"),
        log_file=cfg.get("log_file"),
    )
    logger = logging.getLogger("main")

    project_id = cfg["project_id"]
    tables = parse_tables(cfg["tables"])
    email_cfg = cfg.get("email", {})

    logger.info("=" * 60)
    logger.info("Data Quality Checker starting")
    logger.info("Project : %s", project_id)
    logger.info("Tables  : %s", ", ".join(t.name for t in tables))
    logger.info("=" * 60)

    client = bigquery.Client(project=project_id)
    checker = DataQualityChecker(project_id=project_id, client=client)

    results = checker.run_all_checks(tables)

    # Pretty console summary
    summary_rows = [
        [
            r.table_name,
            r.check_type,
            "✅ PASS" if r.passed else "❌ FAIL",
            r.details,
        ]
        for r in results
    ]
    print("\n" + tabulate(
        summary_rows,
        headers=["Table", "Check", "Status", "Details"],
        tablefmt="grid",
    ))

    failures = [r for r in results if not r.passed]
    logger.info("-" * 60)
    logger.info(
        "Finished: %d total checks, %d failed",
        len(results),
        len(failures),
    )

    # Email alert on any failure
    send_alert(results, email_cfg)

    # Exit code 1 if any check failed (useful for CI / Airflow / cron)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
