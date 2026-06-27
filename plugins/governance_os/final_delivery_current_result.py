"""User-facing current-result text for exhausted final delivery recovery."""

from __future__ import annotations

from typing import Any


CONTEXT_LABELS = {
    "admission_track": "전형",
    "admission_year": "입시 연도",
    "artifact_path": "생성된 파일 경로",
    "channel_permission": "첨부 가능한 채널 권한",
    "html_source": "HTML 원본",
    "life_record_evidence": "생기부 근거",
    "media_tag": "첨부 파일 태그",
    "region": "지역",
    "requested_universities": "요청 대학/학과",
    "source_content": "정리할 원문",
    "student_identity": "학생명",
    "student_score": "학생 성적",
    "student_subjects": "학생 교과 성적",
    "target_university": "지원 대학/학과",
    "visual_review": "시각 검수 결과",
}


def compose_current_result(evidence: dict[str, Any]) -> str:
    playbook = _playbook_from_evidence(evidence)
    label = _result_label(playbook)
    inputs = _required_inputs(playbook, evidence)
    if inputs:
        return f"현재 결론: {label} 없음.\n필요한 입력: {', '.join(inputs)}."
    return "현재 결론: 확정 산출물 없음.\n필요한 입력: 요청을 판단할 원자료."


def _playbook_from_evidence(evidence: dict[str, Any]) -> Any | None:
    decision = evidence.get("decision") if isinstance(evidence, dict) else {}
    playbook_key = ""
    if isinstance(decision, dict):
        playbook_key = str(decision.get("playbook_key") or "").strip()
    playbook_key = playbook_key or str(evidence.get("playbook_key") or "").strip()
    if not playbook_key:
        return None
    try:
        from .registry import load_builtin_registry
        from .versioning import load_runtime_registry
    except Exception:
        return None

    try:
        runtime_playbook = load_runtime_registry().playbooks.get(playbook_key)
    except Exception:
        runtime_playbook = None
    if runtime_playbook is not None:
        return runtime_playbook
    try:
        return load_builtin_registry().playbooks.get(playbook_key)
    except Exception:
        return None


def _result_label(playbook: Any | None) -> str:
    if playbook is None:
        return "확정 산출물"
    delivery = str(getattr(playbook, "delivery_format", "") or "").casefold()
    key = str(getattr(playbook, "key", "") or "").casefold()
    required = " ".join(str(tool) for tool in getattr(playbook, "required_tools", ()) or ())
    blob = " ".join((delivery, key, required)).casefold()
    if "score" in blob or "점수" in blob:
        return "확정 환산점수"
    if "candidate" in blob or "recommend" in blob or "reco" in blob:
        return "확정 추천 산출물"
    if "pdf" in blob or "attachment" in blob or "media" in blob:
        return "확정 PDF 첨부본"
    return "확정 산출물"


def _required_inputs(playbook: Any | None, evidence: dict[str, Any]) -> list[str]:
    if playbook is not None:
        labels = [_context_label(item) for item in getattr(playbook, "required_context", ()) or ()]
        return _unique(labels)
    decision = evidence.get("decision") if isinstance(evidence, dict) else {}
    if not isinstance(decision, dict):
        return []
    retry_tools = decision.get("retry_tools")
    if retry_tools:
        return ["원자료", "생성된 산출물"]
    return []


def _context_label(value: object) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    return CONTEXT_LABELS.get(key, key.replace("_", " "))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result
