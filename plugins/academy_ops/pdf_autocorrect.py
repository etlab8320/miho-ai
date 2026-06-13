"""PDF content 자동 보정 — 반려-재시도 왕복 대신 HTML 생성 시 기계적 결함을 흡수.

학종·실기 리포트 도구가 공유한다. 미호(gpt-5.5)가 content를 한 번 보내면
도구가 빈 표 행을 걷어내고 너무 긴 텍스트를 페이지에 맞게 잘라, 빈칸/페이지
잘림 때문에 반려하던 왕복(2026-06-13 서연 리포트 5분+ 사고)을 없앤다.

금지문구·내용 품질(정성 키워드·전형구조·gap_plan)은 자동 보정하지 않는다 —
금지어 자동 삭제는 문장을 깨고("제외하고"→"하고"), 내용은 LLM이 써야 하기
때문. 그건 schema+grounding이 한 번에 모아 반려한다.
"""

from __future__ import annotations

from typing import Any


def _clamp_str(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def clamp_text_fields(obj: Any, limit: int) -> Any:
    """모든 문자열 값을 limit자로 절단 — 페이지 넘침(잘림)을 원천 차단."""
    if isinstance(obj, str):
        return _clamp_str(obj, limit)
    if isinstance(obj, dict):
        return {k: clamp_text_fields(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clamp_text_fields(v, limit) for v in obj]
    return obj


def drop_incomplete_rows(content: dict[str, Any], table_specs: list[tuple[str, tuple[str, ...]]]) -> None:
    """표 행 중 필수 칸이 빈 행을 제거 — 빈칸 인쇄 대신 그 행을 생략한다.

    table_specs: [("section.subsection.rows", ("col1", "col2")), ...]
    점(.)으로 중첩 경로를 따라가 리스트를 찾고, 각 dict 행의 필수 키가
    모두 채워졌는지 본다. content는 in-place로 수정된다.
    """
    for path, required in table_specs:
        parts = path.split(".")
        node: Any = content
        for p in parts[:-1]:
            if isinstance(node, dict):
                node = node.get(p)
            else:
                node = None
                break
        if not isinstance(node, dict):
            continue
        key = parts[-1]
        rows = node.get(key)
        if not isinstance(rows, list):
            continue
        kept = [
            r for r in rows
            if isinstance(r, dict) and all(str(r.get(c) or "").strip() for c in required)
        ]
        node[key] = kept


def autocorrect(
    content: dict[str, Any],
    *,
    table_specs: list[tuple[str, tuple[str, ...]]],
    char_limit: int,
) -> dict[str, Any]:
    """빈 표 행 제거 + 텍스트 길이 상한. content 사본을 반환한다."""
    if not isinstance(content, dict):
        return content
    corrected = clamp_text_fields(content, char_limit)
    drop_incomplete_rows(corrected, table_specs)
    return corrected
