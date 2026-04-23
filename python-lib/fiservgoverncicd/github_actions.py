"""GitHub Actions polling and artifact download helpers.

This module provides a small helper to:
- wait for a workflow run triggered by a branch push
- wait until it completes (or time out)
- download the first (or named) artifact
- extract a report file from the artifact zip

It is designed to be used inside a Dataiku plugin runnable.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowReport:
    run_id: int
    status: str
    conclusion: Optional[str]
    html_url: Optional[str]
    head_sha: Optional[str]
    artifact_name: str
    report_path: str
    report_content: str


def _download_artifact_zip(archive_download_url: str, github_token: str, timeout_seconds: int) -> bytes:
    """Download an artifact zip without leaking token to the redirect host."""

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json",
    }

    # GitHub returns a redirect to a signed URL; do NOT forward Authorization.
    r = requests.get(
        archive_download_url,
        headers=headers,
        timeout=timeout_seconds,
        allow_redirects=False,
    )
    if r.status_code not in (302, 301, 307, 308):
        r.raise_for_status()
        raise RuntimeError(
            f"Expected redirect when downloading artifact, got status {r.status_code}"
        )

    redirect_url = r.headers.get("Location")
    if not redirect_url:
        raise RuntimeError("Artifact download response missing Location header")

    r2 = requests.get(redirect_url, timeout=timeout_seconds)
    r2.raise_for_status()
    return r2.content


def _download_run_logs_zip(repo_full_name: str, run_id: int, github_token: str, timeout_seconds: int) -> bytes:
    """Download a workflow run logs zip.

    This is different from artifacts: logs are available even if the workflow
    does not upload any artifacts.
    """

    if not repo_full_name:
        raise ValueError("Missing repo_full_name")

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json",
    }

    url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs"
    r = requests.get(url, headers=headers, timeout=timeout_seconds, allow_redirects=False)
    if r.status_code not in (302, 301, 307, 308):
        r.raise_for_status()
        raise RuntimeError(f"Expected redirect when downloading run logs, got {r.status_code}")

    redirect_url = r.headers.get("Location")
    if not redirect_url:
        raise RuntimeError("Run logs download response missing Location header")

    # Signed URL (S3/GCS). Don't forward Authorization.
    r2 = requests.get(redirect_url, timeout=timeout_seconds)
    r2.raise_for_status()
    return r2.content


def wait_for_scan_and_download(
    *,
    branch_name: str,
    github_token: str,
    repo,
    expected_head_sha: Optional[str] = None,
    report_path: str = "scan_report.txt",
    artifact_name: Optional[str] = None,
    prefer_logs_over_artifacts: bool = True,
    poll_interval_seconds: int = 10,
    max_start_wait_seconds: int = 120,
    max_complete_wait_seconds: int = 20 * 60,
    http_timeout_seconds: int = 60,
) -> WorkflowReport:
    """Wait for a GitHub Actions run and download a report artifact.

    Args:
        branch_name: Branch to watch for workflow runs.
        github_token: Token used to authenticate artifact download.
        repo: PyGithub repository object.
        report_path: File inside the artifact zip to extract.
        artifact_name: If provided, selects this artifact name; otherwise first artifact.
        poll_interval_seconds: Sleep between status polls.
        max_start_wait_seconds: Max time waiting for a run to appear.
        max_complete_wait_seconds: Max time waiting for the run to complete.
        http_timeout_seconds: Requests timeout for artifact download.

    Returns:
        WorkflowReport containing the extracted report content and run metadata.

    Raises:
        TimeoutError: If the run never starts or never completes in time.
        RuntimeError: If artifacts/report file cannot be fetched.
        ValueError: If required arguments are missing.
    """

    if not branch_name:
        raise ValueError("Missing required branch_name")
    if not github_token:
        raise ValueError("Missing required github_token")

    logger.info(
        "Waiting for GitHub Actions run to start (branch=%s head_sha=%s)",
        branch_name,
        expected_head_sha,
    )

    run = None
    start_deadline = time.time() + max_start_wait_seconds
    while time.time() < start_deadline:
        runs = repo.get_workflow_runs(branch=branch_name)
        if getattr(runs, "totalCount", 0) > 0:
            # Prefer the run matching the expected commit SHA (avoids grabbing a
            # cancelled run for an earlier commit while the final run is still
            # being registered by GitHub).
            for candidate in runs:
                candidate_sha = getattr(candidate, "head_sha", None)
                if expected_head_sha is None or candidate_sha == expected_head_sha:
                    run = candidate
                    break

        if run is not None:
            break

        time.sleep(5)

    if run is None:
        raise TimeoutError(
            f"Timed out waiting for workflow run to start for branch '{branch_name}'"
        )

    logger.info("Workflow run started (run_id=%s)", run.id)

    complete_deadline = time.time() + max_complete_wait_seconds
    while True:
        run.update()
        if run.status == "completed":
            logger.info("Workflow run completed (conclusion=%s)", run.conclusion)
            break
        if time.time() >= complete_deadline:
            raise TimeoutError(
                f"Timed out waiting for workflow run {run.id} to complete (branch={branch_name})"
            )
        time.sleep(poll_interval_seconds)

    # Preferred: use run logs (works even when no artifacts exist).
    if prefer_logs_over_artifacts:
        repo_full_name = getattr(repo, "full_name", None)
        if repo_full_name:
            try:
                logger.info("Downloading workflow run logs (run_id=%s)", run.id)
                logs_zip = _download_run_logs_zip(
                    repo_full_name=repo_full_name,
                    run_id=run.id,
                    github_token=github_token,
                    timeout_seconds=http_timeout_seconds,
                )
                # Pick the first log file in the zip. (Callers can later provide
                # a specific path if needed.)
                with zipfile.ZipFile(io.BytesIO(logs_zip)) as zf:
                    names = [n for n in zf.namelist() if not n.endswith("/")]
                    if not names:
                        raise RuntimeError("Run logs zip contains no files")
                    chosen_path = names[0]
                    report_content = zf.read(chosen_path).decode("utf-8", errors="replace")

                return WorkflowReport(
                    run_id=run.id,
                    status=run.status,
                    conclusion=run.conclusion,
                    html_url=getattr(run, "html_url", None),
                    head_sha=getattr(run, "head_sha", None),
                    artifact_name="(run logs)",
                    report_path=chosen_path,
                    report_content=report_content,
                )
            except Exception as err:
                logger.warning("Failed to download run logs (run_id=%s): %s", run.id, err)

    # Fallback: artifacts (requires workflow upload-artifact step).
    artifacts = run.get_artifacts()
    if getattr(artifacts, "totalCount", 0) <= 0:
        logger.warning(
            "No artifacts found for workflow run %s (conclusion=%s)",
            run.id,
            run.conclusion,
        )
        return WorkflowReport(
            run_id=run.id,
            status=run.status,
            conclusion=run.conclusion,
            html_url=getattr(run, "html_url", None),
            head_sha=getattr(run, "head_sha", None),
            artifact_name="",
            report_path="",
            report_content=(
                "No artifacts found for this workflow run. "
                "If you expect a report file, ensure the workflow uploads an artifact."
            ),
        )

    artifact = None
    if artifact_name:
        for a in artifacts:
            if a.name == artifact_name:
                artifact = a
                break
        if artifact is None:
            logger.warning(
                "Artifact '%s' not found on run %s (count=%s)",
                artifact_name,
                run.id,
                artifacts.totalCount,
            )
            return WorkflowReport(
                run_id=run.id,
                status=run.status,
                conclusion=run.conclusion,
                html_url=getattr(run, "html_url", None),
                head_sha=getattr(run, "head_sha", None),
                artifact_name="",
                report_path="",
                report_content=(
                    f"Artifact '{artifact_name}' not found on workflow run. "
                    "Check workflow configuration."
                ),
            )
    else:
        artifact = artifacts[0]

    logger.info("Downloading artifact '%s' (run_id=%s)", artifact.name, run.id)

    zip_bytes = _download_artifact_zip(
        artifact.archive_download_url,
        github_token=github_token,
        timeout_seconds=http_timeout_seconds,
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # If the caller didn’t supply a valid file path, attempt a fallback.
        chosen_path = report_path
        if chosen_path not in zf.namelist():
            # Pick the first non-directory entry as a best-effort.
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                raise RuntimeError(f"Artifact '{artifact.name}' zip contains no files")
            chosen_path = names[0]

        report_content = zf.read(chosen_path).decode("utf-8", errors="replace")

    return WorkflowReport(
        run_id=run.id,
        status=run.status,
        conclusion=run.conclusion,
        html_url=getattr(run, "html_url", None),
        head_sha=getattr(run, "head_sha", None),
        artifact_name=artifact.name,
        report_path=chosen_path,
        report_content=report_content,
    )
