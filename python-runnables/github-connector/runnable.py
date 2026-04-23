"""Dataiku runnable: sync bundle to GitHub and fetch scan report."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import dataiku
from dataiku.runnables import Runnable

from fiservgoverncicd.orchestrator import run_github_scan

logger = logging.getLogger(__name__)


class MyRunnable(Runnable):
    """Runnable entrypoint for the github-connector plugin component."""

    def __init__(self, project_key: str, config: Dict[str, Any], plugin_config: Dict[str, Any]):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        self.client = dataiku.api_client()

        # Config are items passed through the runnable UI.
        self.bundle_id: Optional[str] = self.config.get("bundle_id")
        self.github_repo: Optional[str] = self.config.get("github_repo")

        # plugin_config are items passed through plugin settings.
        self.folders_to_skip = self.plugin_config.get("folders_to_skip", [])
        self.github_token: Optional[str] = self.plugin_config.get("github_token")

        # Optional knobs (can be added to runnable.json later if desired)
        self.artifact_name: Optional[str] = self.config.get("artifact_name")
        self.report_path: str = self.config.get("report_path", "scan_report.txt")

    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        if not self.bundle_id:
            raise ValueError("Missing required parameter: bundle_id")
        if not self.github_repo:
            raise ValueError("Missing required parameter: github_repo")
        if not self.github_token:
            raise ValueError("Missing required plugin setting: github_token")


        logger.info(
            "Starting bundle sync + GitHub Actions scan (project=%s bundle=%s repo=%s)",
            self.project_key,
            self.bundle_id,
            self.github_repo,
        )

        html_result = run_github_scan(
            client=self.client,
            project_key=self.project_key,
            bundle_id=self.bundle_id,
            github_repo=self.github_repo,
            github_token=self.github_token,
            folders_to_skip=self.folders_to_skip,
            artifact_name=self.artifact_name,
            report_path=self.report_path,
        )

        return html_result
