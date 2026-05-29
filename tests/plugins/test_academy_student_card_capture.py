from pathlib import Path
from types import SimpleNamespace

from plugins.academy_ops import student_card_capture


def test_capture_html_to_png_falls_back_when_snap_blocks_hidden_output(
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
        if output_path == image_path:
            return SimpleNamespace(returncode=0, stderr="Permission denied", stdout="")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nfallback")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(student_card_capture.subprocess, "run", fake_run)

    student_card_capture.capture_html_to_png(html_path, image_path, width=600, height=320)

    assert image_path.read_bytes().startswith(b"\x89PNG")
    assert len(calls) == 2
    assert f"--screenshot={image_path}" in calls[0]
    assert any(str(tmp_path / "miho_chromium_captures") in arg for arg in calls[1])
