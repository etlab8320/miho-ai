"""학종 정성 프로필 조회 — susi27_student_record_qualitative.sqlite3.

학종 리포트의 알맹이는 전형 구조 숫자가 아니라 "이 대학이 서류에서 무엇을
중점적으로 보는가"다. 그 답이 이 DB의 final_ready 프로필(검토축·읽는 방식,
원하는 생기부 키워드, 과목별 노트, 면접/서류 방어 질문, 최근 입결 참고값)에
있다. hakjong_report_contract는 처음부터 qualitative_profile을 근거 도구로
요구했지만 실제 도구가 등록된 적이 없어 미호가 읽을 길이 없었다
(2026-06-12 실사고: "학종 DB를 안 본 느낌").
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .hakjong_live_research import (
    latest_live_research_bundle as _latest_live_research_bundle,
    live_research_bundle as _live_research_bundle,
    write_live_research_bundle as _write_live_research_bundle,
)

_DEFAULT_DB = (
    "~/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/"
    "threads/thread__1513557600497565696/work/susi27_pipeline/"
    "susi27_student_record_qualitative.sqlite3"
)

_JSON_FIELDS = (
    "evaluation_elements_json",
    "desired_record_keywords_json",
    "subject_specific_notes_json",
    "interview_points_json",
)


def _db_path() -> Path:
    return Path(os.environ.get("MIHO_HAKJONG_QUALITATIVE_DB") or _DEFAULT_DB).expanduser()


def _loads(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def lookup_profiles(
    university: str | None = None,
    department: str | None = None,
    admission_track: str | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    path = _db_path()
    if not path.exists():
        return {"ok": False, "error": f"학종 정성 DB가 없다: {path}"}

    clauses = ["status = 'final_ready'"]
    params: list[Any] = []
    for col, val in (
        ("university", university),
        ("department", department),
        ("admission_track", admission_track),
    ):
        if val and str(val).strip():
            clauses.append(f"{col} LIKE ?")
            params.append(f"%{str(val).strip()}%")

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT * FROM qualitative_profiles WHERE "
            + " AND ".join(clauses)
            + " ORDER BY university, department LIMIT ?",
            (*params, max(1, min(int(limit or 4), 10))),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return {
            "ok": True,
            "profiles": [],
            "note": (
                "final_ready 정성 프로필이 없는 전형이다 — 이 경우 평가 중점은 "
                "추측하지 말고 전형 구조(susi27_rule_lookup)와 생기부 사실만으로 쓴다."
            ),
        }

    profiles = []
    for r in rows:
        live_research = _live_research_bundle(
            path,
            university=r["university"],
            department=r["department"],
            admission_track=r["admission_track"],
        )
        profiles.append(
            {
                "university": r["university"],
                "department": r["department"],
                "admission_track": r["admission_track"],
                "summary": r["summary_1000"],
                "evaluation_elements": _loads(r["evaluation_elements_json"]),
                "desired_record_keywords": _loads(r["desired_record_keywords_json"]),
                "subject_specific_notes": _loads(r["subject_specific_notes_json"]),
                "interview_points": _loads(r["interview_points_json"]),
                "recent_result_avg_grade": r["recent_result_avg_grade"],
                "recent_result_note": r["recent_result_note"],
                "live_research": live_research,
            }
        )
    return {"ok": True, "profiles": profiles}


def _handler(args: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    payload = args or {}
    return lookup_profiles(
        university=payload.get("university"),
        department=payload.get("department"),
        admission_track=payload.get("admission_track"),
        limit=int(payload.get("limit") or 4),
    )


def register_hakjong_qualitative_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="hakjong_qualitative_profile",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "university": {"type": "string", "description": "대학명 일부 또는 전체."},
                "department": {"type": "string", "description": "선택: 학과/모집단위명 일부."},
                "admission_track": {"type": "string", "description": "선택: 전형명 일부. 예: 자기추천, 네오르네상스."},
                "limit": {"type": "integer", "default": 4, "minimum": 1, "maximum": 10},
            },
            "required": ["university"],
            "additionalProperties": False,
        },
        handler=_handler,
        description=(
            "학종(학생부종합) 정성 프로필 조회 — 학종 리포트·학종 상담 체인의 필수 첫 단계. "
            "대학이 서류에서 중점적으로 보는 것(검토축·읽는 방식), 생기부에 박혀 있어야 할 키워드, "
            "과목별 기록 노트, 면접/서류 방어 질문, 최근 입결 참고값을 반환한다. "
            "조회 시마다 교수진·최근논문·최신뉴스 live search를 시도해 "
            "school_specific_source_bundles/*live_research_auto*.json으로 저장하고 live_research로 함께 반환한다. "
            "academy_hakjong_report_package를 호출하기 전에 반드시 이 도구로 해당 전형 프로필을 "
            "확인하고, 객관진단·보완전략을 이 평가 기준과 live_research 흐름에 맞춰 써라. "
            "프로필이 없는 전형은 평가 중점을 추측하지 말 것."
        ),
    )
