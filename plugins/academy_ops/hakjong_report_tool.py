"""Academy tool for packaging validated hakjong PDFs for delivery."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

from .hakjong_report_contract import validate_hakjong_report


def _hakjong_report_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    html_path = Path(str(payload.get("html_path") or "")).expanduser()
    pdf_path = Path(str(payload.get("pdf_path") or "")).expanduser()
    expected_pages = int(payload.get("expected_pages") or 4)

    report = validate_hakjong_report(
        html_path=html_path,
        pdf_path=pdf_path,
        student_name=str(payload.get("student_name") or ""),
        university_name=str(payload.get("university_name") or ""),
        department_name=str(payload.get("department_name") or ""),
        track_name=str(payload.get("track_name") or ""),
        student_stage=str(payload.get("student_stage") or ""),
        expected_pages=expected_pages,
        evidence_tools=[str(item) for item in payload.get("evidence_tools") or []],
        page_image_paths=[Path(str(item)).expanduser() for item in payload.get("page_image_paths") or []],
        contact_sheet_path=(
            Path(str(payload.get("contact_sheet_path"))).expanduser()
            if payload.get("contact_sheet_path")
            else None
        ),
    )
    if not report["ok"]:
        return json.dumps(
            {
                "ok": False,
                "message": "학종 PDF 검증 실패. 고정 템플릿으로 다시 생성해야 해.",
                "errors": report["errors"],
                "warnings": report["warnings"],
                "checks": report["checks"],
            },
            ensure_ascii=False,
        )

    out_dir = get_miho_home() / "media_cache" / "susi_student_record" / "validated"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(
        str(payload.get("student_name") or ""),
        str(payload.get("university_name") or ""),
        str(payload.get("department_name") or ""),
    )
    packaged_pdf = _copy_unique(pdf_path, out_dir / f"{stem}.pdf")
    packaged_html = _copy_unique(html_path, out_dir / f"{stem}.html")
    manifest_path = packaged_pdf.with_suffix(".hakjong_validation.json")
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "pdf_path": str(packaged_pdf),
                "html_path": str(packaged_html),
                "source_pdf_path": str(pdf_path),
                "source_html_path": str(html_path),
                "checks": report["checks"],
                "warnings": report["warnings"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    media_tag = f"MEDIA:{packaged_pdf}"
    return json.dumps(
        {
            "ok": True,
            "message": f"학종 PDF 검증 통과. {media_tag}",
            "file_path": str(packaged_pdf),
            "html_path": str(packaged_html),
            "manifest_path": str(manifest_path),
            "media_tag": media_tag,
            "checks": report["checks"],
        },
        ensure_ascii=False,
    )


def register_hakjong_report_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_hakjong_report_package",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "html_path": {"type": "string", "description": "생성된 학종 리포트 HTML 절대경로."},
                "pdf_path": {"type": "string", "description": "생성된 학종 리포트 PDF 절대경로."},
                "student_name": {"type": "string", "description": "표지/본문/파일에서 일치해야 하는 학생명."},
                "university_name": {"type": "string", "description": "표지/본문에서 일치해야 하는 대학명."},
                "department_name": {"type": "string", "description": "표지/본문에서 일치해야 하는 학과명."},
                "track_name": {"type": "string", "description": "표지/본문에서 일치해야 하는 전형명."},
                "student_stage": {
                    "type": "string",
                    "description": "리포트 목적을 결정하는 학생 상태. grade1/grade2/grade3/graduate 또는 고1/고2/고3/N수생.",
                },
                "evidence_tools": {
                    "type": "array",
                    "description": "실제 근거 조회에 사용한 도구/소스 이름. 1/2학년은 상담/학생맥락 근거와 학종 프로파일, 3학년/N수생은 life_record_*와 학종 프로파일이 필요하다.",
                    "items": {"type": "string"},
                },
                "page_image_paths": {
                    "type": "array",
                    "description": "PDF 각 페이지를 렌더링한 PNG 절대경로 목록. expected_pages와 개수가 같아야 한다.",
                    "items": {"type": "string"},
                },
                "contact_sheet_path": {
                    "type": "string",
                    "description": "전체 페이지를 한 번에 검수하기 위한 contact sheet PNG 절대경로.",
                },
                "expected_pages": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                    "description": "고정 템플릿 기준 페이지 수. 기본 4.",
                },
            },
            "required": [
                "html_path",
                "pdf_path",
                "student_name",
                "university_name",
                "student_stage",
                "evidence_tools",
                "page_image_paths",
                "contact_sheet_path",
            ],
            "additionalProperties": False,
        },
        handler=_hakjong_report_package_tool_handler,
        description=(
            "학생부종합전형/학종 상담 PDF를 학생·학부모에게 전달하기 직전에 반드시 쓰는 검증·패키징 도구. "
            "라우팅 문구를 하드코딩하지 않는다. 이미 생성한 HTML/PDF가 locked premium_hakjong_report 템플릿, "
            "MAX 로고/맥스체대입시 일산교육원/푸터/KPI/A4 세로/페이지 수/학생명·학교·학과·전형 일치를 만족하는지 검사한다. "
            "통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 media_tag를 반환한다. "
            "student_stage별 목적이 맞는지 검사한다. 1학년은 상담 기반 생활기록부 시작 설계, 2학년은 1학년 기록과 2학년 설계, "
            "3학년은 1학기 입력 전 보완과 지원 판단, N수생/졸업생은 완성 학생부 분석과 면접 방어 중심이어야 한다. "
            "필요 근거, 학종/입시 프로파일 근거, 페이지별 PNG, contact sheet가 없으면 실패한다. "
            "ok:false면 절대 파일을 전달하지 말고 고정 템플릿과 근거 도구로 다시 생성해야 한다."
        ),
    )


def _safe_stem(*parts: str) -> str:
    raw = "_".join(part.strip() for part in parts if part and part.strip())
    clean = re.sub(r"[^\w가-힣.-]+", "_", raw, flags=re.UNICODE).strip("_.")
    return clean[:120] or "hakjong_report"


def _copy_unique(source: Path, target: Path) -> Path:
    resolved_source = source.resolve()
    candidate = target
    counter = 2
    while candidate.exists():
        try:
            if candidate.resolve() == resolved_source:
                return candidate
        except OSError:
            pass
        candidate = target.with_name(f"{target.stem}_{counter}{target.suffix}")
        counter += 1
    shutil.copy2(source, candidate)
    return candidate
