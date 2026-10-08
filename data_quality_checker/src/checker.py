"""
Data Quality Checker core logic.
Performs null, duplicate, and row-count checks between BigQuery source & target tables.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Result of a single data-quality check."""

    table_name: str
    check_type: str          # "nulls" | "duplicates" | "row_count"
    passed: bool
    details: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class TableConfig:
    name: str
    source: str
    target: str
    primary_keys: list[str]
    critical_columns: list[str]
    null_threshold_pct: float = 0.0


class DataQualityChecker:
    """Runs data-quality checks between source and target BigQuery tables."""

    def __init__(self, project_id: str, client: bigquery.Client | None = None):
        self.project_id = project_id
        self.client = client or bigquery.Client(project=project_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all_checks(self, tables: list[TableConfig]) -> list[CheckResult]:
        """Execute every configured check and return results."""
        results: list[CheckResult] = []
        for table in tables:
            logger.info("Starting checks for table: %s", table.name)
            results.extend(self._check_nulls(table))
            results.extend(self._check_duplicates(table))
            results.append(self._check_row_counts(table))
        return results

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_nulls(self, table: TableConfig) -> list[CheckResult]:
        """Check null percentages on critical columns in the *target* table."""
        results: list[CheckResult] = []
        if not table.critical_columns:
            return results

        cols = ", ".join(f"`{c}`" for c in table.critical_columns)
        query = f"""
            SELECT
                COUNT(*) AS total_rows,
                {", ".join(
                    f"COUNTIF(`{c}` IS NULL) AS null_{c}"
                    for c in table.critical_columns
                )}
            FROM `{table.target}`
        """
        df = self._query_to_df(query)
        total = int(df["total_rows"].iloc[0]) if not df.empty else 0

        for col in table.critical_columns:
            null_count = int(df[f"null_{col}"].iloc[0]) if total > 0 else 0
            null_pct = (null_count / total * 100) if total > 0 else 0.0
            passed = null_pct <= table.null_threshold_pct

            details = (
                f"Column `{col}`: {null_count:,} nulls "
                f"({null_pct:.2f}%) out of {total:,} rows "
                f"(threshold: {table.null_threshold_pct}%)"
            )
            results.append(
                CheckResult(
                    table_name=table.name,
                    check_type="nulls",
                    passed=passed,
                    details=details,
                    metrics={
                        "column": col,
                        "null_count": null_count,
                        "total_rows": total,
                        "null_pct": round(null_pct, 4),
                        "threshold_pct": table.null_threshold_pct,
                    },
                )
            )
            level = logging.INFO if passed else logging.WARNING
            logger.log(level, "[%s] %s -> %s", table.name, "PASS" if passed else "FAIL", details)

        return results

    def _check_duplicates(self, table: TableConfig) -> list[CheckResult]:
        """Detect duplicate primary/business keys in the *target* table."""
        if not table.primary_keys:
            return []

        key_cols = ", ".join(f"`{k}`" for k in table.primary_keys)
        query = f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT CONCAT({", ".join(f"CAST(`{k}` AS STRING)" for k in table.primary_keys)})) AS distinct_keys
            FROM `{table.target}`
        """
        df = self._query_to_df(query)
        total = int(df["total_rows"].iloc[0]) if not df.empty else 0
        distinct = int(df["distinct_keys"].iloc[0]) if total > 0 else 0
        duplicates = total - distinct
        passed = duplicates == 0

        details = (
            f"Primary key(s) [{', '.join(table.primary_keys)}]: "
            f"{duplicates:,} duplicate row(s) "
            f"({total:,} total / {distinct:,} distinct)"
        )
        result = CheckResult(
            table_name=table.name,
            check_type="duplicates",
            passed=passed,
            details=details,
            metrics={
                "primary_keys": table.primary_keys,
                "total_rows": total,
                "distinct_keys": distinct,
                "duplicate_rows": duplicates,
            },
        )
        level = logging.INFO if passed else logging.WARNING
        logger.log(level, "[%s] %s -> %s", table.name, "PASS" if passed else "FAIL", details)
        return [result]

    def _check_row_counts(self, table: TableConfig) -> CheckResult:
        """Compare row counts between source and target tables."""
        query = f"""
            SELECT
                (SELECT COUNT(*) FROM `{table.source}`) AS source_count,
                (SELECT COUNT(*) FROM `{table.target}`) AS target_count
        """
        df = self._query_to_df(query)
        source_cnt = int(df["source_count"].iloc[0])
        target_cnt = int(df["target_count"].iloc[0])
        diff = abs(source_cnt - target_cnt)
        passed = source_cnt == target_cnt

        details = (
            f"Row count mismatch: source={source_cnt:,}  target={target_cnt:,}  "
            f"difference={diff:,}"
            if not passed
            else f"Row counts match: {source_cnt:,} rows"
        )
        result = CheckResult(
            table_name=table.name,
            check_type="row_count",
            passed=passed,
            details=details,
            metrics={
                "source_count": source_cnt,
                "target_count": target_cnt,
                "difference": diff,
            },
        )
        level = logging.INFO if passed else logging.WARNING
        logger.log(level, "[%s] %s -> %s", table.name, "PASS" if passed else "FAIL", details)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _query_to_df(self, query: str) -> pd.DataFrame:
        """Execute a BigQuery SQL query and return a pandas DataFrame."""
        logger.debug("Running query:\n%s", query)
        job = self.client.query(query)
        return job.to_dataframe(create_bqstorage_client=False)
