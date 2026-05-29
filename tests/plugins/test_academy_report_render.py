"""Tests for the academy_report_image tool handler + registration."""

from __future__ import annotations

import json

import plugins.academy_ops.report_render_tool as t
from plugins.academy_ops.report_render_tool import (
    _report_image_tool_handler,
    register_report_image_tool,
)


class _FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, **kw):
        self.tools[name] = kw


def test_tool_registers_with_expected_name():
    ctx = _FakeCtx()
    register_report_image_tool(ctx)
    assert "academy_report_image" in ctx.tools
    assert ctx.tools["academy_report_image"]["handler"] is _report_image_tool_handler


def test_handler_renders_contract_to_image(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        captured["height"] = kw.get("height")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)

    res = _report_image_tool_handler(
        {
            "title": "월말 보고서",
            "columns": [{"key": "j", "label": "제멀", "unit": "cm"}],
            "groups": [
                {
                    "label": "남",
                    "kind": "male",
                    "avg_label": "평균",
                    "rows": [{"name": "가", "meta": "고3", "j": 295}],
                }
            ],
        }
    )
    data = json.loads(res)
    assert data["ok"] is True
    assert "MEDIA:" in data["message"]
    # the rendered HTML carries the column label and value (contract honoured)
    assert "제멀" in captured["html"]
    assert "295" in captured["html"]
    assert captured["height"] >= 720


def test_handler_rejects_missing_columns():
    assert json.loads(_report_image_tool_handler({"title": "T", "groups": [{"rows": []}]}))["ok"] is False


def test_handler_rejects_missing_groups():
    assert json.loads(
        _report_image_tool_handler({"title": "T", "columns": [{"key": "a", "label": "A"}]})
    )["ok"] is False


def test_handler_passes_best_direction(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake_capture(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(t, "capture_html_to_png", fake_capture)
    _report_image_tool_handler(
        {
            "title": "T",
            "columns": [{"key": "run", "label": "20m", "unit": "초", "best": "low"}],
            "groups": [{"rows": [{"name": "가", "run": 15.0}, {"name": "나", "run": 13.0}]}],
        }
    )
    # lower-is-better → minimum highlighted
    assert '<span class="best">13' in captured["html"]
