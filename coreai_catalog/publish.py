"""
Core AI Catalog — release/publish workflow helpers.

This module contains the pure, testable logic used by the ``publish`` CLI
command: version bumping, pre-flight checks, git operations, build, and
upload orchestration.  The thin CLI wrapper lives in ``cli.cmd_publish``.

All shell-facing functions are kept minimal so that tests can mock
``subprocess.run`` (and ``_run``, which is the single choke point for
subprocess execution) without touching the filesystem or network.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import yaml


# ── Version helpers ─────────────────────────────────────────────────────

_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def validate_version(version: str) -> str:
    """Return *version* if it is a valid semantic version string, else raise.

    Accepts ``MAJOR.MINOR.PATCH`` (no pre-release / build metadata).
    """
    if not isinstance(version, str) or not _VERSION_RE.match(version.strip()):
        raise ValueError(
            f"Invalid version '{version}'. "
            "Expected MAJOR.MINOR.PATCH (e.g. 2.1.0)."
        )
    return version.strip()


def suggest_next_version(current: str, bump: str = "patch") -> str:
    """Suggest the next version from *current* given a bump type.

    Args:
        current: Current ``MAJOR.MINOR.PATCH`` version.
        bump: One of ``major``, ``minor``, ``patch`` (default).

    Returns:
        The next version string.

    Raises:
        ValueError: If *current* is not valid or *bump* is unknown.
    """
    current = validate_version(current)
    parts = [int(p) for p in current.split(".")]
    if bump == "major":
        parts = [parts[0] + 1, 0, 0]
    elif bump == "minor":
        parts = [parts[0], parts[1] + 1, 0]
    elif bump == "patch":
        parts = [parts[0], parts[1], parts[2] + 1]
    else:
        raise ValueError(
            f"Unknown bump type '{bump}'. Expected major, minor, or patch."
        )
    return ".".join(str(p) for p in parts)


def bump_version_in_catalog_yaml(path: Path, new_version: str) -> None:
    """Update ``metadata.version`` in a catalog.yaml file.

    Uses PyYAML round-tripping to preserve structure.  Only the
    ``metadata.version`` key is changed.

    Args:
        path: Path to ``catalog.yaml``.
        new_version: The new version string (validated first).
    """
    new_version = validate_version(new_version)
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if data is None:
        raise ValueError(f"catalog.yaml at {path} is empty or unreadable")
    if "metadata" not in data or "version" not in (data["metadata"] or {}):
        raise ValueError(
            f"catalog.yaml at {path} has no metadata.version key"
        )
    data["metadata"]["version"] = new_version
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False,
                              allow_unicode=True))


def bump_version_in_pyproject(path: Path, new_version: str) -> None:
    """Update ``version = "x.y.z"`` in a pyproject.toml file.

    This is a targeted regex replacement so we don't need a full TOML
    parser and preserve the file as closely as possible.

    Args:
        path: Path to ``pyproject.toml``.
        new_version: The new version string (validated first).
    """
    new_version = validate_version(new_version)
    path = Path(path)
    content = path.read_text()
    pattern = re.compile(
        r'(^version\s*=\s*["\'])\d+\.\d+\.\d+(["\'])',
        re.MULTILINE,
    )
    new_content, count = pattern.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}", content
    )
    if count == 0:
        raise ValueError(
            f"Could not find 'version = \"...\"' in {path}"
        )
    path.write_text(new_content)


def bump_version_in_agent_json(path: Path, new_version: str) -> None:
    """Update the top-level ``version`` field in ``agent.json``.

    Uses a targeted regex on the first ``"version": "x.y.z"`` occurrence so
    the file's formatting (indentation, key order) is preserved exactly.

    Args:
        path: Path to ``agent.json``.
        new_version: The new version string (validated first).
    """
    new_version = validate_version(new_version)
    path = Path(path)
    content = path.read_text()
    pattern = re.compile(r'("version"\s*:\s*")\d+\.\d+\.\d+(")')
    new_content, count = pattern.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}", content, count=1
    )
    if count == 0:
        raise ValueError(f"Could not find '\"version\": \"x.y.z\"' in {path}")
    path.write_text(new_content)


def bump_version_in_openapi_yaml(path: Path, new_version: str) -> None:
    """Update ``info.version`` in ``openapi.yaml``.

    Targets the single ``version: x.y.z`` line whose value is a bare
    semver (the schema's ``version: { type: string }`` lines don't match).

    Args:
        path: Path to ``openapi.yaml``.
        new_version: The new version string (validated first).
    """
    new_version = validate_version(new_version)
    path = Path(path)
    content = path.read_text()
    pattern = re.compile(
        r"^(\s*version:\s*['\"]?)\d+\.\d+\.\d+(['\"]?)\s*$",
        re.MULTILINE,
    )
    new_content, count = pattern.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}", content
    )
    if count != 1:
        raise ValueError(
            f"Expected exactly 1 semver 'version:' line in {path}, found {count}"
        )
    path.write_text(new_content)


def bump_version_in_readme(path: Path, new_version: str) -> None:
    """Update the ``**Version:** vX.Y.Z`` badge line in ``README.md``.

    Args:
        path: Path to ``README.md``.
        new_version: The new version string (validated first).
    """
    new_version = validate_version(new_version)
    path = Path(path)
    content = path.read_text()
    pattern = re.compile(r"(\*\*Version:\*\*\s*v)\d+\.\d+\.\d+")
    new_content, count = pattern.subn(
        lambda m: f"{m.group(1)}{new_version}", content, count=1
    )
    if count == 0:
        raise ValueError(f"Could not find '**Version:** vX.Y.Z' in {path}")
    path.write_text(new_content)


def check_changelog_has_version(path: Path, version: str) -> bool:
    """Return True if ``CHANGELOG.md`` has a ``## [version]`` section.

    This is a hint, not a bump — the changelog entry itself is authored
    content, so publish only warns when it is missing rather than
    fabricating one.
    """
    version = validate_version(version)
    path = Path(path)
    if not path.exists():
        return False
    return bool(re.search(
        rf"^##\s*\[{re.escape(version)}\]", path.read_text(), re.MULTILINE
    ))


def bump_all_version_surfaces(repo_root: Path, new_version: str) -> list[str]:
    """Bump every version surface in the repo to *new_version*.

    Surfaces (the release version contract — see README "Version contract"):
      1. ``catalog.yaml``   → ``metadata.version``
      2. ``pyproject.toml`` → ``version = "..."``
      3. ``agent.json``     → ``"version": "..."``
      4. ``openapi.yaml``   → ``info.version``
      5. ``README.md``      → ``**Version:** vX.Y.Z`` badge
      6. ``CHANGELOG.md``   → checked only (hint when the section is missing)

    Required surfaces (catalog.yaml, pyproject.toml) raise if the file is
    missing; optional surfaces are reported as skipped so older checkouts
    still publish.

    Returns:
        Human-readable status strings, one per surface.
    """
    new_version = validate_version(new_version)
    repo_root = Path(repo_root)
    results: list[str] = []

    bump_version_in_catalog_yaml(repo_root / "catalog.yaml", new_version)
    results.append(f"catalog.yaml → {new_version}")
    bump_version_in_pyproject(repo_root / "pyproject.toml", new_version)
    results.append(f"pyproject.toml → {new_version}")

    optional_surfaces = [
        ("agent.json", bump_version_in_agent_json),
        ("openapi.yaml", bump_version_in_openapi_yaml),
        ("README.md", bump_version_in_readme),
    ]
    for name, bump_fn in optional_surfaces:
        path = repo_root / name
        if path.exists():
            bump_fn(path, new_version)
            results.append(f"{name} → {new_version}")
        else:
            results.append(f"{name} skipped (file not found)")

    if check_changelog_has_version(repo_root / "CHANGELOG.md", new_version):
        results.append(f"CHANGELOG.md has a [{new_version}] section")
    else:
        results.append(
            f"CHANGELOG.md missing a '## [{new_version}]' section — add one "
            "before tagging"
        )
    return results


def read_catalog_version(path: Path) -> str:
    """Read ``metadata.version`` from a catalog.yaml file."""
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    return (data or {}).get("metadata", {}).get("version", "unknown")


def read_pyproject_version(path: Path) -> str:
    """Read the ``version`` field from a pyproject.toml file via regex."""
    path = Path(path)
    content = path.read_text()
    m = re.search(r'^version\s*=\s*["\'](\d+\.\d+\.\d+)["\']', content, re.MULTILINE)
    if not m:
        raise ValueError(f"Could not find version in {path}")
    return m.group(1)


# ── Pre-flight check logic ──────────────────────────────────────────────


class PreflightError(Exception):
    """Raised when a pre-flight check fails."""


def _run(cmd: Sequence[str], *, cwd: Path | None = None,
         check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, streaming output to the parent's stdout/stderr.

    This is the single choke point for subprocess execution in the
    publish workflow.  Tests monkeypatch this function to simulate
    success / failure without running real commands.
    """
    return subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, check=check)


def run_preflight_checks(repo_root: Path, *,
                         runner: Sequence[str] | None = None) -> list[str]:
    """Execute the pre-flight check suite.

    Runs (in order):
      1. ``python scripts/validate.py``
      2. ``python -m pytest``

    Each step is run via :func:`_run`.  If any step returns non-zero
    (or raises :class:`subprocess.CalledProcessError`) a
    :class:`PreflightError` is raised.

    Args:
        repo_root: Path to the repository root (where ``scripts/`` lives).
        runner: Optional override for the Python interpreter command.
            Defaults to ``[sys.executable]``.

    Returns:
        A list of human-readable status strings (one per check).

    Raises:
        PreflightError: If any check fails.
    """
    runner = list(runner) if runner else [sys.executable]
    repo_root = Path(repo_root)
    results: list[str] = []

    # 1. Validate catalog data
    validate_cmd = runner + ["scripts/validate.py"]
    try:
        _run(validate_cmd, cwd=repo_root)
        results.append("✅ validate.py passed")
    except subprocess.CalledProcessError as exc:
        results.append(f"❌ validate.py failed (exit {exc.returncode})")
        raise PreflightError(
            f"Pre-flight check failed: validate.py (exit {exc.returncode})"
        ) from exc

    # 2. Run test suite
    test_cmd = runner + ["-m", "pytest"]
    try:
        _run(test_cmd, cwd=repo_root)
        results.append("✅ pytest passed")
    except subprocess.CalledProcessError as exc:
        results.append(f"❌ pytest failed (exit {exc.returncode})")
        raise PreflightError(
            f"Pre-flight check failed: pytest (exit {exc.returncode})"
        ) from exc

    return results


# ── Build / upload / git orchestration ──────────────────────────────────


def git_commit_and_tag(repo_root: Path, version: str, *,
                       message: str | None = None) -> str:
    """Stage, commit, and tag a release.

    Args:
        repo_root: Path to the git repository.
        version: Version string (validated) — used for tag ``v{version}``.
        message: Optional commit message.  Defaults to ``Release v{version}``.

    Returns:
        The tag name that was created (``v{version}``).

    Raises:
        subprocess.CalledProcessError: If any git command fails.
    """
    version = validate_version(version)
    tag = f"v{version}"
    msg = message or f"Release v{version}"
    repo_root = Path(repo_root)

    _run(["git", "add", "-A"], cwd=repo_root)
    _run(["git", "commit", "-m", msg], cwd=repo_root)
    _run(["git", "tag", tag], cwd=repo_root)
    return tag


def build_dist(repo_root: Path, *, runner: Sequence[str] | None = None) -> None:
    """Build sdist + wheel via ``python -m build``.

    Args:
        repo_root: Repository root (where ``pyproject.toml`` lives).
        runner: Optional Python interpreter override.

    Raises:
        subprocess.CalledProcessError: If the build fails.
    """
    runner = list(runner) if runner else [sys.executable]
    _run(runner + ["-m", "build"], cwd=Path(repo_root))


def upload_to_pypi(repo_root: Path, *, dist_dir: str = "dist") -> None:
    """Upload artifacts to PyPI via ``twine upload dist/*``.

    Requires ``PYPI_API_TOKEN`` to be set in the environment.

    Args:
        repo_root: Repository root.
        dist_dir: Subdirectory containing the built artifacts.

    Raises:
        RuntimeError: If ``PYPI_API_TOKEN`` is not set.
        subprocess.CalledProcessError: If twine fails.
    """
    import os
    if not os.environ.get("PYPI_API_TOKEN"):
        raise RuntimeError(
            "PYPI_API_TOKEN environment variable is not set. "
            "Cannot upload to PyPI."
        )
    repo_root = Path(repo_root)
    dist_glob = str(repo_root / dist_dir / "*")
    _run(["twine", "upload", dist_glob])


def git_push(repo_root: Path) -> None:
    """Push commits + tags to the remote.

    Runs ``git push --follow-tags``.
    """
    _run(["git", "push", "--follow-tags"], cwd=Path(repo_root))
