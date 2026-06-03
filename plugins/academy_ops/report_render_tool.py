"""General-purpose table-report image tool.

The model supplies the data contract (columns/groups/rows); this tool renders
it to a PNG via the shared design system + Chromium capture. The model never
positions values — the renderer places them strictly by column order, so a
header and its values can't drift. Reusable for any tabular report, not just
academy data.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

from .report_design import ColumnSpec, GroupSpec, ReportSpec, estimate_report_height, render_report_html
from .student_card_capture import StudentCardCaptureError, capture_html_to_png, find_browser_executable


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _capture_height(html_path: Path, spec: ReportSpec) -> int:
    measured = _measure_html_height(html_path)
    if measured:
        return max(820, min(8000, measured + 36))
    return estimate_report_height(spec)


def _measure_html_height(html_path: Path) -> int:
    browser = find_browser_executable()
    if browser is None:
        return 0
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1240,900",
        "--dump-dom",
        html_path.as_uri(),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    marker = 'data-render-height="'
    start = result.stdout.find(marker)
    if start < 0:
        return 0
    start += len(marker)
    end = result.stdout.find('"', start)
    if end < 0:
        return 0
    try:
        return int(result.stdout[start:end])
    except ValueError:
        return 0


def _report_image_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    title = str(payload.get("title") or "보고서").strip()
    raw_cols = payload.get("columns") or []
    raw_groups = payload.get("groups") or []
    if not raw_cols:
        return _json_error("보고서를 만들 컬럼(columns)이 필요해.")
    if not raw_groups:
        return _json_error("보고서를 만들 데이터(groups)가 필요해.")

    try:
        columns = [
            ColumnSpec(
                key=str(c["key"]),
                label=str(c.get("label") or c["key"]),
                unit=str(c.get("unit") or ""),
                best=str(c.get("best") or "high"),
            )
            for c in raw_cols
        ]
        groups = [
            GroupSpec(
                label=str(g.get("label") or ""),
                rows=list(g.get("rows") or []),
                kind=str(g.get("kind") or ""),
                avg_label=str(g.get("avg_label") or ""),
            )
            for g in raw_groups
        ]
    except (KeyError, TypeError) as exc:
        return _json_error(f"보고서 형식이 올바르지 않아: {exc}")

    spec = ReportSpec(
        title=title,
        subtitle=str(payload.get("subtitle") or ""),
        columns=columns,
        groups=groups,
        highlight_best=bool(payload.get("highlight_best", True)),
        show_group_avg=bool(payload.get("show_group_avg", True)),
        rank_by=str(payload.get("rank_by") or ""),
        note=str(payload.get("note") or ""),
    )
    html = render_report_html(spec)

    out_dir = get_miho_home() / "media_cache" / "academy_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    html_path = out_dir / f"{stem}.html"
    image_path = out_dir / f"{stem}.png"
    html_path.write_text(html, encoding="utf-8")

    try:
        capture_html_to_png(html_path, image_path, width=1240, height=_capture_height(html_path, spec))
    except StudentCardCaptureError as exc:
        return _json_error(str(exc))

    media_tag = f"MEDIA:{image_path}"
    return json.dumps(
        {
            "ok": True,
            "message": f"{title} 보고서야. {media_tag}",
            "image_path": str(image_path),
            "media_tag": media_tag,
        },
        ensure_ascii=False,
    )


def register_report_image_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_report_image",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "보고서 제목."},
                "subtitle": {"type": "string", "description": "부제/설명 (대상 인원·기준 등)."},
                "columns": {
                    "type": "array",
                    "description": "표의 데이터 컬럼 정의. 순서대로 표시된다.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "rows의 값 키."},
                            "label": {"type": "string", "description": "헤더에 보일 이름."},
                            "unit": {"type": "string", "description": "단위 (cm, 초, kg 등)."},
                            "best": {
                                "type": "string",
                                "enum": ["high", "low", "none"],
                                "description": "우수 방향. 큰 값이 좋으면 high, 시간처럼 작은 값이 좋으면 low, 강조 안 하면 none.",
                            },
                        },
                        "required": ["key", "label"],
                        "additionalProperties": False,
                    },
                },
                "groups": {
                    "type": "array",
                    "description": "데이터 그룹. 성별처럼 평균을 분리해야 하면 그룹을 나눈다.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "그룹 제목 (예: 남학생)."},
                            "kind": {"type": "string", "enum": ["male", "female", ""], "description": "색상/라벨용 구분."},
                            "avg_label": {"type": "string", "description": "평균 행 라벨 (예: 남자 평균). 비우면 평균 행 없음."},
                            "rows": {
                                "type": "array",
                                "description": "행 목록. 각 행은 name, meta(구분), 그리고 columns의 key별 값.",
                                "items": {"type": "object", "additionalProperties": True},
                            },
                        },
                        "required": ["rows"],
                        "additionalProperties": False,
                    },
                },
                "rank_by": {"type": "string", "description": "그룹 내 정렬 기준 컬럼 key (내림차순). 비우면 입력 순서."},
                "highlight_best": {"type": "boolean", "description": "컬럼별 최고기록 강조 여부 (기본 true)."},
                "show_group_avg": {"type": "boolean", "description": "그룹 평균 행 표시 여부 (기본 true)."},
                "note": {"type": "string", "description": "하단 각주."},
            },
            "required": ["title", "columns", "groups"],
            "additionalProperties": False,
        },
        handler=_report_image_tool_handler,
        description=(
            "학원(PACA/Peak) 데이터를 표·명단·기록 이미지로 보여줄 때 쓰는 전용 보고서 렌더러. "
            "사용자가 학생 기록/명단/월말테스트 등을 '표로' 또는 '이미지로' 달라고 하고 기존 전용 도구가 "
            "정확히 맞지 않으면, sports-report-card 같은 일반 보고서 스킬을 쓰지 말고 반드시 이 도구를 써라 "
            "(일반 스킬은 열이 어긋나고 학원 도메인을 모른다). "
            "데이터는 직접 가져오지 않는다 — 이미 가진 행을 rows로 넘겨라. 보통 academy_monthly_test_records / "
            "academy_student_record_lookup 등 기존 조회 도구의 결과에서 개별 항목을 뽑아 columns/groups/rows로 구성한다. "
            "Render ANY tabular data as a polished PNG: the caller decides columns/groups/rows; the renderer "
            "guarantees header-value alignment, computes group averages and per-column bests in code, and stamps "
            "the brand. 남녀처럼 평균을 섞으면 안 될 땐 groups로 나눠라 (체대는 성별 기준이 다르다)."
        ),
    )
