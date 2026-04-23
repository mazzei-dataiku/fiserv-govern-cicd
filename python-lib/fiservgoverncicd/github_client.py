"""GitHub helpers used by the Dataiku plugin.

This module is intentionally small: it provides a single helper to build a
PyGithub repo object from a token and a repository name.

Expected repo format: "owner/repo" (e.g. "my-org/my-repo").
"""

from __future__ import annotations

from typing import Any


def build_github_repo(github_token: str, github_repo: str) -> Any:
    """Create and return a PyGithub repository object.

    Args:
        github_token: Personal access token used to authenticate.
        github_repo: Repository identifier in the form "owner/repo".

    Returns:
        A PyGithub `Repository` object (typed as `Any` to avoid a hard runtime
        dependency on PyGithub types).

    Raises:
        ValueError: If required arguments are missing.
        RuntimeError: If PyGithub is not installed.
    """

    if not github_token:
        raise ValueError("Missing required github_token")

    if not github_repo:
        raise ValueError("Missing required github_repo")

    try:
        from github import Auth, Github  # type: ignore
    except ImportError as err:
        raise RuntimeError(
            "PyGithub is required but not installed (pip package 'PyGithub')."
        ) from err

    auth = Auth.Token(github_token)
    client = Github(auth=auth)
    return client.get_repo(github_repo)
