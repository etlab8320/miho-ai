"""Tests for the general-purpose academy_render_image tool + router fallback."""

from __future__ import annotations

import json

import plugins.academy_ops.natural_router as natural_router
import plugins.academy_ops.render_image_tool as t
from plugins.academy_ops.render_image_tool import (
    _render_image_tool_handler,
    register_render_image_tool,
)


class _FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, **kw):
        self.tools[name] = kw


def test_tool_registers_with_expected_name():
    ctx = _FakeCtx()
    register_render_image_tool(ctx)
    assert "academy_render_image" in ctx.tools
    assert ctx.tools["academy_render_image"]["handler"] is _render_image_tool_handler


def test_handler_renders_html_to_image_media(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        captured["width"] = kw.get("width")
        captured["height"] = kw.get("height")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)

    res = _render_image_tool_handler(
        {
            "html": "<html><body><h1>수요일 명단</h1></body></html>",
            "title": "수요일 출석 명단",
            "width": 900,
            "height": 600,
        }
    )
    data = json.loads(res)
    assert data["ok"] is True
    assert "MEDIA:" in data["message"]
    assert data["media_tag"] == f"MEDIA:{data['image_path']}"
    assert data["image_path"].endswith(".png")
    # the model's content is preserved, and the quality base is injected so the
    # render comes out with aligned numbers and a clean Korean font.
    assert "수요일 명단" in captured["html"]
    assert "tabular-nums" in captured["html"]
    assert "border-collapse" in captured["html"]
    assert captured["width"] == 900
    assert captured["height"] == 600


def test_base_style_injected_first_in_existing_head(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    model_html = (
        "<html><head><style>body{background:#000;}</style></head>"
        "<body><table><tr><td>1</td></tr></table></body></html>"
    )
    _render_image_tool_handler({"html": model_html})
    rendered = captured["html"]
    # base style lands inside the existing head, BEFORE the model's own <style>
    # so the model's styles win on conflicts (CSS source order).
    assert "tabular-nums" in rendered
    assert rendered.index("tabular-nums") < rendered.index("background:#000")
    # the bundled Korean webfont is embedded so render never falls back to a
    # blocky system font.
    assert "@font-face" in rendered


def test_bare_fragment_is_wrapped_into_full_document(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    _render_image_tool_handler({"html": "<table><tr><td>홍길동</td></tr></table>"})
    rendered = captured["html"]
    assert rendered.lstrip().startswith("<!DOCTYPE html>")
    assert "홍길동" in rendered
    assert "tabular-nums" in rendered


def test_handler_uses_defaults_for_missing_dimensions(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["width"] = kw.get("width")
        captured["height"] = kw.get("height")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    _render_image_tool_handler({"html": "<html><body>x</body></html>"})
    assert captured["width"] == 1200
    assert captured["height"] == 1400


def test_handler_clamps_out_of_range_dimensions(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["width"] = kw.get("width")
        captured["height"] = kw.get("height")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    _render_image_tool_handler({"html": "<html><body>x</body></html>", "width": 99999, "height": 1})
    assert captured["width"] == 2400
    assert captured["height"] == 320


def test_handler_rejects_empty_html():
    assert json.loads(_render_image_tool_handler({"html": "   "}))["ok"] is False
    assert json.loads(_render_image_tool_handler({}))["ok"] is False


def test_handler_reports_capture_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def fake_capture(html_path, image_path, **kw):
        raise t.StudentCardCaptureError("브라우저를 찾지 못했어.")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    data = json.loads(_render_image_tool_handler({"html": "<html><body>x</body></html>"}))
    assert data["ok"] is False
    assert "브라우저" in data["message"]


def test_router_prompt_steers_unmatched_image_request_to_allow_plus_render():
    """No-dedicated-tool image/표 requests are guided to ALLOW (body agent), and
    the render-image fallback workflow is surfaced to the resolver LLM — not via
    keyword branching, but as prompt guidance."""
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "이번주 수요일 출석할 학생 명단 이미지로 줘",
            "2026-06-03",
        )
    )
    assert "academy_render_image" in prompt
    assert "action=allow" in prompt
