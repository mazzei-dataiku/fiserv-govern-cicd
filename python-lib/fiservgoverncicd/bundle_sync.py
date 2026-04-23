"""Sync a Dataiku bundle archive to a GitHub branch.

This module:
- Downloads/streams a DSS exported bundle archive (zip)
- Unzips and filters files
- Creates (or reuses) a target branch
- Pushes files into the branch via the GitHub Contents API (PyGithub)

Notes:
- This approach can be API-call heavy for large bundles.
- It is intentionally written to be runnable inside a DSS plugin without
  requiring a local git clone.
"""

from __future__ import annotations

import fnmatch
import io
import logging
import zipfile
from contextlib import closing
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _should_skip(path: str, exclude_prefixes: Iterable[str], exclude_globs: Iterable[str]) -> bool:
    normalized = path.lstrip("/")

    for prefix in exclude_prefixes:
        if normalized.startswith(prefix.lstrip("/")):
            return True

    for pattern in exclude_globs:
        if fnmatch.fnmatch(normalized, pattern):
            return True

    return False


def _read_stream_bytes(stream) -> bytes:
    """Best-effort conversion of Dataiku stream response to bytes."""

    # `dataikuapi` typically returns a `requests.Response`.
    if hasattr(stream, "content"):
        return stream.content

    if hasattr(stream, "read"):
        return stream.read()

    if hasattr(stream, "raw") and hasattr(stream.raw, "read"):
        return stream.raw.read()

    raise TypeError(f"Unsupported stream type: {type(stream)!r}")


def _recreate_branch(repo, branch_name: str, base_branch: str = "main") -> str:
    """Delete and recreate `branch_name` from `base_branch`.

    This matches the "always start from a clean branch" workflow: if the branch
    already exists, it is deleted first.

    Returns:
        The commit SHA of the base branch head used for the new ref.
    """

    if branch_name == base_branch:
        raise ValueError("Refusing to delete the base branch")

    base = repo.get_branch(base_branch)

    try:
        ref = repo.get_git_ref(f"heads/{branch_name}")
    except Exception:
        ref = None

    if ref is not None:
        logger.info("Deleting existing branch '%s'", branch_name)
        try:
            ref.delete()
        except Exception as err:
            raise RuntimeError(f"Failed to delete branch '{branch_name}': {err}") from err

    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base.commit.sha)
    logger.info("Created branch '%s' from '%s'", branch_name, base_branch)
    return base.commit.sha


def sync_bundle_to_github(
    client,
    project_key: str,
    bundle_id: str,
    folders_to_skip: Iterable[str],
    repo,
    *,
    branch_name: Optional[str] = None,
    base_branch: str = "main",
) -> str:
    """Stream a Dataiku bundle and push its contents to GitHub.

    Args:
        client: A `dataikuapi.DSSClient` (or compatible) instance.
        project_key: DSS project key that owns the bundle.
        bundle_id: Exported bundle id/name.
        folders_to_skip: List of project_config subfolders to exclude.
        repo: PyGithub repository object.
        branch_name: Branch to create/update (defaults to `bundle_id`).
        base_branch: Base branch for initial ref creation.

    Raises:
        RuntimeError: On critical failures (download/unzip/push).
        ValueError: If required args are missing.
    """

    if not project_key:
        raise ValueError("Missing required project_key")
    if not bundle_id:
        raise ValueError("Missing required bundle_id")

    target_branch = branch_name or bundle_id

    project = client.get_project(project_key)

    exclude_prefixes = [f"project_config/{d.strip('/')}/" for d in folders_to_skip if d]
    exclude_globs = ["**/.git/**", ".git/**", "**/.DS_Store", "**/__MACOSX/**"]

    stream = None
    try:
        logger.info("Streaming bundle '%s' from project '%s'", bundle_id, project_key)
        stream = project.get_exported_bundle_archive_stream(bundle_id)

        base_sha = _recreate_branch(repo, target_branch, base_branch=base_branch)

        bundle_bytes = _read_stream_bytes(stream)
        zip_contents = io.BytesIO(bundle_bytes)

        with zipfile.ZipFile(zip_contents) as zf:
            for file_info in zf.infolist():
                if file_info.is_dir():
                    continue

                path = file_info.filename
                if _should_skip(path, exclude_prefixes=exclude_prefixes, exclude_globs=exclude_globs):
                    continue

                file_bytes = zf.read(path)
                try:
                    # Create if missing, otherwise update.
                    try:
                        existing = repo.get_contents(path, ref=target_branch)
                        repo.update_file(
                            path=path,
                            message=f"Sync {path} from bundle {bundle_id}",
                            content=file_bytes,
                            sha=existing.sha,
                            branch=target_branch,
                        )
                    except Exception:
                        repo.create_file(
                            path=path,
                            message=f"Sync {path} from bundle {bundle_id}",
                            content=file_bytes,
                            branch=target_branch,
                        )

                    logger.info("Pushed '%s'", path)
                except Exception as err:
                    logger.warning("Failed to push '%s': %s", path, err)

        try:
            # Best-effort: retrieve the current head SHA after all file commits.
            head_sha = repo.get_branch(target_branch).commit.sha
        except Exception:
            head_sha = base_sha

        logger.info("Bundle sync complete (branch=%s head_sha=%s)", target_branch, head_sha)
        return head_sha

    except Exception as err:
        raise RuntimeError(f"Critical error during bundle sync: {err}") from err

    finally:
        if stream is not None:
            try:
                # Some stream objects are `requests.Response` and have `close()`.
                with closing(stream):
                    pass
            except Exception:
                try:
                    stream.close()
                except Exception:
                    pass
            logger.info("Bundle stream closed")
