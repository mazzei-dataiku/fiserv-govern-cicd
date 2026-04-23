"""High-level orchestration for the GitHub connector runnable."""

from __future__ import annotations

import html
import logging
from typing import Iterable, Optional

from fiservgoverncicd.bundle_sync import sync_bundle_to_github
from fiservgoverncicd.github_actions import WorkflowReport, wait_for_scan_and_download
from fiservgoverncicd.github_client import build_github_repo
from fiservgoverncicd.scan_report_renderer import (
    scan_report_to_html_table,
    scan_report_to_markdown_table,
)

logger = logging.getLogger(__name__)


def _render_report_html(report: WorkflowReport) -> str:
    meta_rows = [
        ("Run ID", str(report.run_id)),
        ("Status", report.status),
        ("Conclusion", report.conclusion or ""),
        ("Artifact", report.artifact_name),
        ("Report file", report.report_path),
        ("Run URL", report.html_url or ""),
    ]

    meta_html = "".join(
        f"<tr><th style='text-align:left;padding-right:12px'>{html.escape(k)}</th>"
        f"<td>{html.escape(v)}</td></tr>"
        for k, v in meta_rows
    )

    # Match the original demo: a few status lines + a markdown table.
    status_lines = [
        f"Scan started (ID: {report.run_id}). Monitoring status...",
        f"Scan finished with conclusion: {report.conclusion}",
    ]

    if report.artifact_name:
        status_lines.append(f"Downloading {report.artifact_name}...")
        status_lines.append(f"Successfully downloaded {report.artifact_name}...")

    markdown_report = scan_report_to_markdown_table(report.report_content, title="Code Scan Report")

    return (
        "<h2>GitHub Actions Scan Report</h2>"
        "<table>"
        f"{meta_html}"
        "</table>"
        "<h3>Output</h3>"
        "<pre style='white-space:pre-wrap'>"
        + html.escape("\n".join(status_lines))
        + "</pre>"
        "<h3>Report</h3>"
        "<pre style='white-space:pre-wrap'>"
        f"{html.escape(markdown_report)}"
        "</pre>"
    )


def run_github_scan(
    *,
    client,
    project_key: str,
    bundle_id: str,
    github_repo: str,
    github_token: str,
    folders_to_skip: Iterable[str],
    artifact_name: Optional[str] = None,
    report_path: str = "scan_report.txt",
    poll_interval_seconds: int = 10,
    max_start_wait_seconds: int = 60,
    max_complete_wait_seconds: int = 20 * 60,
) -> str:
    """Orchestrate: push bundle -> wait for GH action -> return HTML."""

    repo = build_github_repo(github_token=github_token, github_repo=github_repo)

    # 1) Sync bundle contents into a branch
    head_sha = sync_bundle_to_github(
        client=client,
        project_key=project_key,
        bundle_id=bundle_id,
        folders_to_skip=folders_to_skip,
        repo=repo,
        branch_name=bundle_id,
    )

    # 2) Wait for workflow + download report
    report = wait_for_scan_and_download(
        branch_name=bundle_id,
        github_token=github_token,
        repo=repo,
        expected_head_sha=head_sha,
        report_path=report_path,
        artifact_name=artifact_name,
        prefer_logs_over_artifacts=False,
        poll_interval_seconds=poll_interval_seconds,
        max_start_wait_seconds=max_start_wait_seconds,
        max_complete_wait_seconds=max_complete_wait_seconds,
    )

    return _render_report_html(report)
