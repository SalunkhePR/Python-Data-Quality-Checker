"""
Email alerting for data-quality failures.
"""

from __future__ import annotations

import logging
import os
import smtplib
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from src.checker import CheckResult

logger = logging.getLogger(__name__)


def send_alert(
    results: list[CheckResult],
    email_cfg: dict[str, Any],
) -> None:
    """
    Send an HTML email summarizing failed checks.
    Only sends when there is at least one failure and email is enabled.
    """
    if not email_cfg.get("enabled", False):
        logger.info("Email alerting is disabled - skipping.")
        return

    failures = [r for r in results if not r.passed]
    if not failures:
        logger.info("All checks passed - no email will be sent.")
        return

    password = os.getenv(email_cfg.get("password_env", "EMAIL_PASSWORD"))
    if not password:
        logger.error(
            "Email password not found in environment variable '%s'. "
            "Alert will not be sent.",
            email_cfg.get("password_env"),
        )
        return

    subject = f"{email_cfg.get('subject_prefix', '[Data Quality Alert]')} {len(failures)} check(s) failed"
    body_html = _build_html_body(results, failures)
    body_plain = _build_plain_body(failures)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender"]
    msg["To"] = ", ".join(email_cfg["recipients"])
    msg.attach(MIMEText(body_plain, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(email_cfg["sender"], password)
            server.sendmail(
                email_cfg["sender"],
                email_cfg["recipients"],
                msg.as_string(),
            )
        logger.info("Alert email sent to %s", email_cfg["recipients"])
    except Exception as exc:
        logger.exception("Failed to send alert email: %s", exc)


def _build_html_body(all_results: list[CheckResult], failures: list[CheckResult]) -> str:
    # Group failures by table for cleaner display
    by_table: dict[str, list[CheckResult]] = defaultdict(list)
    for r in failures:
        by_table[r.table_name].append(r)

    sections = []
    for table_name, checks in by_table.items():
        rows = []
        for r in checks:
            rows.append(
                f"""
                <tr>
                  <td style="padding:8px;border:1px solid #ddd;">{r.check_type}</td>
                  <td style="padding:8px;border:1px solid #ddd;color:#dc3545;font-weight:bold;">FAIL</td>
                  <td style="padding:8px;border:1px solid #ddd;">{r.details}</td>
                </tr>
                """
            )
        section_html = f"""
        <h3 style="margin-top:24px;margin-bottom:8px;color:#333;">Table: {table_name}</h3>
        <table style="border-collapse:collapse;width:100%;font-size:14px;">
          <thead>
            <tr style="background-color:#f8f9fa;">
              <th style="padding:8px;border:1px solid #ddd;text-align:left;">Check</th>
              <th style="padding:8px;border:1px solid #ddd;text-align:left;">Status</th>
              <th style="padding:8px;border:1px solid #ddd;text-align:left;">Details</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        """
        sections.append(section_html)

    passed_count = len(all_results) - len(failures)

    return f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
      </head>
      <body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#333;max-width:800px;margin:0 auto;padding:20px;">
        <h2 style="color:#dc3545;margin-bottom:4px;">Data Quality Alert</h2>
        <p style="margin-top:0;color:#666;">Automated check results</p>

        <div style="background-color:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px 16px;margin:16px 0;">
          <strong>{len(failures)}</strong> check(s) failed &nbsp;|&nbsp;
          <strong>{passed_count}</strong> passed &nbsp;|&nbsp;
          <strong>{len(all_results)}</strong> total
        </div>

        {"".join(sections)}

        <p style="margin-top:32px;font-size:12px;color:#999;border-top:1px solid #eee;padding-top:12px;">
          This is an automated message from the Data Quality Checker.<br>
          Please investigate the failed checks above.
        </p>
      </body>
    </html>
    """


def _build_plain_body(failures: list[CheckResult]) -> str:
    lines = [
        "DATA QUALITY ALERT",
        "=" * 40,
        f"{len(failures)} check(s) failed:",
        "",
    ]
    current_table = None
    for r in failures:
        if r.table_name != current_table:
            current_table = r.table_name
            lines.append(f"\n[{current_table}]")
        lines.append(f"  - {r.check_type.upper()}: {r.details}")
    lines.append("\n" + "=" * 40)
    lines.append("This is an automated message from the Data Quality Checker.")
    return "\n".join(lines)