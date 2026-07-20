"""DocForge private-mode adapter for scanned student-record safety."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

DOCFORGE_PRIVATE_TIMEOUT_SECONDS = 45
DOCFORGE_FIRST_PAGE = "1"


class PrivatePdfReviewError(RuntimeError):
    """Raised with safe Korean copy when local private review cannot run."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def read_private_first_page_text(
    document: Path,
    *,
    runner: Runner = subprocess.run,
) -> str:
    """Read page one through DocForge private mode without cloud fallback."""
    with tempfile.TemporaryDirectory(prefix="miho_life_record_private_gate_") as tmp:
        output = Path(tmp) / "result"
        _run_private_page(document, output, runner=runner)
        return _evidence_text(output / "evidence.json")


def _run_private_page(document: Path, output: Path, *, runner: Runner) -> None:
    launcher = shutil.which("et-pdf")
    if not launcher:
        raise PrivatePdfReviewError(
            "로컬 PDF 검수 도구를 찾지 못해 스캔 생기부 처리를 중단했어."
        )
    command = [
        launcher,
        "process",
        str(document),
        "--mode",
        "private",
        "--pages",
        DOCFORGE_FIRST_PAGE,
        "--output",
        str(output),
    ]
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=DOCFORGE_PRIVATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PrivatePdfReviewError(
            "로컬에서 스캔 생기부를 읽는 시간이 길어져 안전하게 중단했어."
        ) from exc
    except OSError as exc:
        raise PrivatePdfReviewError(
            "로컬 PDF 검수 도구를 실행하지 못해 스캔 생기부 처리를 중단했어."
        ) from exc
    if completed.returncode != 0:
        raise PrivatePdfReviewError(
            "스캔 생기부를 로컬에서 읽지 못해 자동 저장을 중단했어. 원본을 확인해줘."
        )


def _evidence_text(path: Path) -> str:
    evidence = _read_json(path)
    parts: list[str] = []
    for page in evidence.get("pages") or []:
        for block in page.get("blocks") or []:
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts)


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivatePdfReviewError(
            "로컬 PDF 검수 결과를 확인하지 못해 자동 저장을 중단했어."
        ) from exc
    if not isinstance(value, dict):
        raise PrivatePdfReviewError(
            "로컬 PDF 검수 결과 형식이 올바르지 않아 자동 저장을 중단했어."
        )
    return value


__all__ = [
    "PrivatePdfReviewError",
    "read_private_first_page_text",
]
