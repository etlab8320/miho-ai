"""Capture academy card HTML to PNG with a local Chromium-family browser."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


class StudentCardCaptureError(RuntimeError):
    pass


def capture_html_to_png(html_path: Path, image_path: Path, *, width: int = 1200, height: int = 1400) -> None:
    browser = find_browser_executable()
    if browser is None:
        raise StudentCardCaptureError(
            "학생카드 이미지를 만들 브라우저를 찾지 못했어. Chrome 또는 Edge 설치가 필요해."
        )
    image_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={image_path}",
        html_path.as_uri(),
    ]
    if sys.platform.startswith("linux"):
        command.insert(1, "--no-sandbox")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudentCardCaptureError("학생카드 이미지 캡처가 시간 안에 끝나지 않았어.") from exc
    if result.returncode != 0 or not image_path.exists():
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f" ({detail[:160]})" if detail else ""
        raise StudentCardCaptureError(f"학생카드 이미지 캡처에 실패했어.{suffix}")


def find_browser_executable() -> str | None:
    env_path = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH", "").strip()
    if env_path:
        resolved = _resolve_candidate(env_path)
        if resolved:
            return resolved
    for candidate in _browser_candidates():
        resolved = _resolve_candidate(candidate)
        if resolved:
            return resolved
    return None


def _resolve_candidate(candidate: str) -> str | None:
    expanded = os.path.expanduser(candidate)
    if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
        return expanded
    found = shutil.which(candidate)
    return found if found else None


def _browser_candidates() -> list[str]:
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "google-chrome",
            "chromium",
            "chrome",
        ]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        program_files = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]
        paths = [
            Path(local) / "Google/Chrome/Application/chrome.exe",
            Path(local) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for root in program_files:
            if root:
                paths.extend(
                    [
                        Path(root) / "Google/Chrome/Application/chrome.exe",
                        Path(root) / "Microsoft/Edge/Application/msedge.exe",
                    ]
                )
        return [str(path) for path in paths] + ["chrome.exe", "msedge.exe"]
    return ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]
