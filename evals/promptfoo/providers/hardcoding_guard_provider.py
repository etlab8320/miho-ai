from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
SKIP_NAMES = {"hardcoding_guard_provider.py"}
SKIP_DIRS_FOR_DEFAULT_SCAN = {"tests"}
TEXT_SUFFIXES = {
    ".js",
    ".json",
    ".jsx",
    ".mjs",
    ".py",
    ".sh",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

RULES = (
    ("absolute user path", re.compile(r"(/Users/[^'\"\s]+|/home/[^'\"\s]+|[A-Za-z]:\\\\Users\\\\[^'\"\s]+)")),
    ("hardcoded miho home", re.compile(r"(~/.miho|Path\.home\(\)\s*/\s*[\"']\.miho[\"'])")),
    ("secret-shaped literal", re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,})\b")),
)


def _configured_paths(config: dict[str, Any]) -> tuple[list[str], bool]:
    paths = config.get("paths")
    if isinstance(paths, str):
        return [part for part in paths.split(",") if part.strip()], False
    if isinstance(paths, list):
        return [str(path) for path in paths], False

    env_paths = os.environ.get("MIHO_HARDCODING_PATHS")
    if env_paths:
        return [part for part in env_paths.split(",") if part.strip()], False
    return _changed_files(), True


def _changed_files() -> list[str]:
    files: list[str] = []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        result = None
    if result is not None:
        files.extend(line for line in result.stdout.splitlines() if line.strip())

    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        untracked = None
    if untracked is not None:
        files.extend(line for line in untracked.stdout.splitlines() if line.strip())
    return sorted(set(files))


def _target_files(paths: Iterable[str], *, skip_tests: bool) -> list[Path]:
    targets: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.is_dir():
            targets.extend(
                child
                for child in path.rglob("*")
                if child.is_file() and child.suffix in TEXT_SUFFIXES
            )
        elif path.is_file() and path.suffix in TEXT_SUFFIXES:
            targets.append(path)
    resolved = sorted({target.resolve() for target in targets})
    if not skip_tests:
        return resolved
    return [
        target
        for target in resolved
        if "tests" not in target.relative_to(REPO_ROOT).parts
    ]


def _scan_file(path: Path) -> list[str]:
    if path.name in SKIP_NAMES:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []

    findings: list[str] = []
    for number, line in enumerate(lines, start=1):
        for label, pattern in RULES:
            if pattern.search(line):
                findings.append(f"{path}:{number}: {label}")
    return findings


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Promptfoo provider that reports hardcoded local paths and secrets."""
    config = options.get("config", {})
    del prompt, context
    paths, from_default_scan = _configured_paths(config)
    files = _target_files(paths, skip_tests=from_default_scan)
    findings: list[str] = []
    for path in files:
        findings.extend(_scan_file(path))

    if findings:
        body = "\n".join(f"- {finding}" for finding in findings[:30])
        return {"output": f"하드코딩 경고: {len(findings)}건 발견\n{body}"}
    return {"output": f"하드코딩 검사 완료: {len(files)}개 파일에서 경고 없음"}
