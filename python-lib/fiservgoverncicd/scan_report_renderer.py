"""Render a plain-text scan report into HTML.

Expected input format (one finding per line):
    path/to/file.py:12:34: E999 Some message

This matches common linter-like outputs: file:line:col: CODE description
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ScanFinding:
    file_path: str
    line: int
    column: int
    error_code: str
    description: str


_FINDING_RE = re.compile(r"^(.*?):(\d+):(\d+):\s(\w\d+)\s(.*)$")


def parse_scan_report(report_content: str) -> List[ScanFinding]:
    """Parse text report content into structured findings."""

    findings: List[ScanFinding] = []
    for raw_line in report_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _FINDING_RE.match(line)
        if not match:
            continue

        file_path, line_num, column, code, desc = match.groups()
        file_path = file_path.replace("./", "")

        findings.append(
            ScanFinding(
                file_path=file_path,
                line=int(line_num),
                column=int(column),
                error_code=code,
                description=desc,
            )
        )

    return findings


def scan_report_to_html_table(
    report_content: str,
    *,
    title: str = "Code Scan Report",
    empty_message: str = "No issues found. Code is clean.",
    include_raw_in_details: bool = True,
) -> str:
    """Convert scan report content into an HTML table.

    Returns a self-contained HTML snippet suitable for DSS runnable `resultType=HTML`.
    """

    findings = parse_scan_report(report_content)

    if not findings:
        empty_html = f"<h3>{html.escape(title)}</h3><p>{html.escape(empty_message)}</p>"
        if include_raw_in_details and report_content.strip():
            empty_html += (
                "<details><summary>Raw report</summary>"
                "<pre style='white-space:pre-wrap'>"
                f"{html.escape(report_content)}"
                "</pre></details>"
            )
        return empty_html

    header = (
        "<tr>"
        "<th style='text-align:left'>File Path</th>"
        "<th style='text-align:left'>Line</th>"
        "<th style='text-align:left'>Column</th>"
        "<th style='text-align:left'>Error Code</th>"
        "<th style='text-align:left'>Description</th>"
        "</tr>"
    )

    rows = []
    for f in findings:
        rows.append(
            "<tr>"
            f"<td>{html.escape(f.file_path)}</td>"
            f"<td>{f.line}</td>"
            f"<td>{f.column}</td>"
            f"<td><code>{html.escape(f.error_code)}</code></td>"
            f"<td>{html.escape(f.description)}</td>"
            "</tr>"
        )

    table = (
        f"<h3>{html.escape(title)}</h3>"
        "<table>"
        f"{header}"
        f"{''.join(rows)}"
        "</table>"
    )

    if include_raw_in_details:
        table += (
            "<details><summary>Raw report</summary>"
            "<pre style='white-space:pre-wrap'>"
            f"{html.escape(report_content)}"
            "</pre></details>"
        )

    return table
