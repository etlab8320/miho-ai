from pathlib import Path
import stat
from types import SimpleNamespace

from plugins.academy_ops import student_card_capture


def test_find_browser_executable_uses_playwright_chromium_cache(monkeypatch, tmp_path: Path) -> None:
    browser = tmp_path / ".cache/ms-playwright/chromium-123/chrome-linux/chrome"
    browser.parent.mkdir(parents=True)
    browser.write_text("#!/bin/sh\n", encoding="utf-8")
    browser.chmod(browser.stat().st_mode | stat.S_IXUSR)

    monkeypatch.delenv("AGENT_BROWSER_EXECUTABLE_PATH", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(student_card_capture.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(student_card_capture.sys, "platform", "linux")
    monkeypatch.setattr(student_card_capture.shutil, "which", lambda _candidate: None)

    assert student_card_capture.find_browser_executable() == str(browser)


def test_find_browser_executable_uses_playwright_browsers_path(monkeypatch, tmp_path: Path) -> None:
    cache = tmp_path / "pw"
    browser = cache / "chromium_headless_shell-456/chrome-linux/headless_shell"
    browser.parent.mkdir(parents=True)
    browser.write_text("#!/bin/sh\n", encoding="utf-8")
    browser.chmod(browser.stat().st_mode | stat.S_IXUSR)

    monkeypatch.delenv("AGENT_BROWSER_EXECUTABLE_PATH", raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    monkeypatch.setattr(student_card_capture.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(student_card_capture.sys, "platform", "linux")
    monkeypatch.setattr(student_card_capture.shutil, "which", lambda _candidate: None)

    assert student_card_capture.find_browser_executable() == str(browser)


def test_capture_html_to_png_stages_hidden_output_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hidden_home = tmp_path / ".miho"
    html_path = tmp_path / "card.html"
    html_path.write_text("<html><body>card</body></html>", encoding="utf-8")
    image_path = hidden_home / "cache/media/card.png"
    calls: list[list[str]] = []

    monkeypatch.setattr(student_card_capture, "find_browser_executable", lambda: "chromium-browser")
    monkeypatch.setattr(student_card_capture.Path, "home", lambda: tmp_path)

    def fake_run(command, **kwargs):
        calls.append(command)
        screenshot_arg = next(arg for arg in command if arg.startswith("--screenshot="))
        output_path = Path(screenshot_arg.split("=", 1)[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nfallback")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(student_card_capture.subprocess, "run", fake_run)

    student_card_capture.capture_html_to_png(html_path, image_path, width=600, height=320)

    assert image_path.read_bytes().startswith(b"\x89PNG")
    assert len(calls) == 1
    assert any(str(tmp_path / "miho_chromium_captures") in arg for arg in calls[0])
    assert f"--screenshot={image_path}" not in calls[0]


def test_capture_html_to_png_stages_hidden_input_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hidden_home = tmp_path / ".miho"
    html_path = hidden_home / "cache/media/card.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>card</body></html>", encoding="utf-8")
    image_path = hidden_home / "cache/media/card.png"
    calls: list[list[str]] = []

    monkeypatch.setattr(student_card_capture, "find_browser_executable", lambda: "chromium-browser")
    monkeypatch.setattr(student_card_capture.Path, "home", lambda: tmp_path)

    def fake_run(command, **kwargs):
        calls.append(command)
        assert str(html_path.as_uri()) not in command
        screenshot_arg = next(arg for arg in command if arg.startswith("--screenshot="))
        output_path = Path(screenshot_arg.split("=", 1)[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nstaged-input")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(student_card_capture.subprocess, "run", fake_run)

    student_card_capture.capture_html_to_png(html_path, image_path, width=600, height=320)

    assert image_path.read_bytes().startswith(b"\x89PNG")
    assert len(calls) == 1
    assert any(str(tmp_path / "miho_chromium_captures") in arg for arg in calls[0])
