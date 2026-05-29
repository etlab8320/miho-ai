"""Capture academy card HTML to PNG with a local Chromium-family browser."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


class StudentCardCaptureError(RuntimeError):
    pass


def capture_html_to_png(html_path: Path, image_path: Path, *, width: int = 1200, height: int = 1400) -> None:
    browser = find_browser_executable()
    if browser is None:
        raise StudentCardCaptureError(
            "학생카드 이미지를 만들 브라우저를 찾지 못했어. Chrome 또는 Edge 설치가 필요해."
        )
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if _should_use_home_staging(html_path, image_path):
        staged_result = _capture_through_home_staging(
            browser, html_path, image_path, width=width, height=height
        )
        if staged_result.returncode == 0 and image_path.exists():
            return
        _raise_capture_error(staged_result)

    result = _run_capture(browser, html_path, image_path, width=width, height=height)
    if result.returncode == 0 and image_path.exists():
        return

    _raise_capture_error(result)


def _capture_through_home_staging(
    browser: str,
    html_path: Path,
    image_path: Path,
    *,
    width: int,
    height: int,
) -> subprocess.CompletedProcess[str]:
    staged_html = _home_staging_path(html_path)
    staged_image = _home_staging_path(image_path)
    staged_html.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, staged_html)
    try:
        result = _run_capture(browser, staged_html, staged_image, width=width, height=height)
        if result.returncode == 0 and staged_image.exists():
            shutil.copy2(staged_image, image_path)
        return result
    finally:
        for path in (staged_html, staged_image):
            try:
                path.unlink()
            except OSError:
                pass


def _run_capture(
    browser: str,
    html_path: Path,
    image_path: Path,
    *,
    width: int,
    height: int,
) -> subprocess.CompletedProcess[str]:
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
        return subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudentCardCaptureError("학생카드 이미지 캡처가 시간 안에 끝나지 않았어.") from exc


def _should_use_home_staging(html_path: Path, image_path: Path) -> bool:
    return _path_has_hidden_part(html_path) or _path_has_hidden_part(image_path)


def _path_has_hidden_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.expanduser().parts)


def _home_staging_path(image_path: Path) -> Path:
    suffix = image_path.suffix or ".png"
    return Path.home() / "miho_chromium_captures" / f"{image_path.stem}-{uuid.uuid4().hex}{suffix}"


def _raise_capture_error(result: subprocess.CompletedProcess[str]) -> None:
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
            *_playwright_browser_candidates(),
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
        return [
            str(path) for path in paths
        ] + ["chrome.exe", "msedge.exe", *_playwright_browser_candidates()]
    return [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        *_playwright_browser_candidates(),
    ]


def _playwright_browser_candidates() -> list[str]:
    candidates: list[str] = []
    for root in _playwright_search_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.name.startswith(("chromium-", "chromium_headless_shell-")):
                continue
            candidates.extend(str(path) for path in _playwright_executables(child))
    return candidates


def _playwright_search_roots() -> list[Path]:
    roots: list[Path] = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path and env_path != "0":
        roots.append(Path(os.path.expanduser(env_path)))
    home = Path.home()
    roots.append(home / ".cache" / "ms-playwright")
    if sys.platform == "darwin":
        roots.append(home / "Library" / "Caches" / "ms-playwright")
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        roots.append(Path(local) / "ms-playwright")
    return roots


def _playwright_executables(browser_dir: Path) -> list[Path]:
    if os.name == "nt":
        return [browser_dir / "chrome-win" / "chrome.exe", browser_dir / "chrome-win" / "headless_shell.exe"]
    if sys.platform == "darwin":
        return [
            browser_dir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            browser_dir / "chrome-mac" / "headless_shell",
        ]
    return [browser_dir / "chrome-linux" / "chrome", browser_dir / "chrome-linux" / "headless_shell"]
