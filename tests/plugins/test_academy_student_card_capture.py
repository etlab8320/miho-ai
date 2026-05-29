from pathlib import Path
from types import SimpleNamespace

from plugins.academy_ops import student_card_capture


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
