"""Grounding checks for hakjong premium report content."""

from __future__ import annotations

import re
from typing import Any

from .hakjong_faculty_research import paper_titles_from_bundle
from .hakjong_live_research import live_research_keywords
from .hakjong_stage_contract import normalize_student_stage


_BROAD_TERMS = {
    "스포츠",
    "체육",
    "학종",
    "서류",
    "면접",
    "학생부",
    "진로",
    "학업",
    "활동",
    "탐구",
    "평가",
    "데이터",
    "디지털",
    "재활",
    "year",
    "month",
    "day",
    "blog",
    "naver",
    "during",
}
_NOISE_TERMS = (
    "네이버",
    "검색 메뉴",
    "본문 영역",
    "바로가기",
    "지식iN",
    "인플루언서",
    "검색 결과",
    "메뉴 영역",
    "검색옵션",
    "초기화",
    "가이드",
    "Sejong",
    "이미지",
)
_INTERNAL_LABELS = ("학교별 해석 렌즈:", "문제정의:", "측정변수:", "산출물:", "면접 방어:")
_LENS_RULES = (
    {
        "keys": ("재활", "운동처방", "기능평가", "손상", "부상", "스포츠의학"),
        "label": "기능평가·운동처방",
        "problem": "통증·피로·회복 관점의 기능평가 질문을 세운다",
        "variables": "관절 가동범위, 회복시간, 피로도, 동작 안정성",
        "output": "개인별 운동처방 보고서와 손상 예방 체크리스트",
        "defense": "변수 선택 이유와 측정 한계",
    },
    {
        "keys": ("산업", "매니지먼트", "글로벌", "미디어", "이벤트", "경영"),
        "label": "스포츠산업·운영분석",
        "problem": "스포츠 경험을 시장·운영·팬 경험 분석 질문으로 확장한다",
        "variables": "참여자 반응, 운영 지연, 콘텐츠 노출, 만족도",
        "output": "스포츠 이벤트 운영 개선안과 데이터 기반 홍보 제안서",
        "defense": "운영 문제와 데이터 근거",
    },
    {
        "keys": ("운동역학", "운동 생리", "운동생리", "체력측정", "스포츠과학", "생리학"),
        "label": "운동역학·생리측정",
        "problem": "운동 수행 경험을 힘·회복·에너지 대사 측정 질문으로 바꾼다",
        "variables": "속도, 정확도, 심박 회복, 에너지 소모, 자세 변화",
        "output": "운동 수행 데이터 분석 보고서와 그래프 기반 발표",
        "defense": "측정 설계, 오차, 결과 해석의 학업·진로 연결",
    },
    {
        "keys": ("체육교육", "교육", "교직", "지도", "수업", "피드백"),
        "label": "체육수업 설계·피드백",
        "problem": "수행 경험을 다른 학생에게 가르칠 수 있는 수업 설계 질문으로 바꾼다",
        "variables": "동작 오류 유형, 피드백 전후 변화, 참여도, 안전 준수",
        "output": "수업 지도안, 관찰 루브릭, 피드백 기록지",
        "defense": "지도 의도, 학생 반응, 수업 개선 근거",
    },
    {
        "keys": ("공공", "시민", "지역", "건강권", "참여", "윤리", "도핑", "공동체"),
        "label": "공공스포츠·시민건강",
        "problem": "스포츠 윤리 관심을 시민 건강과 공정한 참여 문제로 확장한다",
        "variables": "참여 장벽, 규칙 인식, 건강권 쟁점, 공동체 영향",
        "output": "생활체육 참여 개선안과 스포츠윤리 토론 보고서",
        "defense": "조사 근거에 기반한 공정성·건강권 판단",
    },
)


def apply_gap_plan_grounding(content: dict[str, Any], profile: dict[str, Any] | None) -> bool:
    """Inject school-specific DB/live-research anchors into gap_plan subjects."""
    if not isinstance(content, dict) or not isinstance(profile, dict):
        return False
    subjects = _gap_subjects(content)
    if not subjects:
        return False
    university = content.get("university") if isinstance(content.get("university"), dict) else {}; profile = {**profile, "university": university.get("name", ""), "department": university.get("department", ""), "admission_track": university.get("track", "")}
    terms = _grounding_terms(profile)
    anchors = terms["specific"] or terms["all"]
    if not anchors:
        return False
    lens = _school_lens(profile, terms)

    changed = False
    for index, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        current_text = _content_text(subject)
        needs_clean = _has_forbidden_visible_text(current_text)
        if needs_clean:
            _sanitize_subject(subject)
            current_text = _content_text(subject)
        needs_anchors = len(_term_hits(current_text, anchors)) < 2
        needs_live = bool(terms["live"]) and len(_term_hits(current_text, terms["live"])) < min(2, len(terms["live"]))
        needs_lens = _lens_missing(current_text, lens)
        if not needs_anchors and not needs_live and not needs_lens and not needs_clean:
            continue
        selected = _rotating_terms(anchors, index, take=2)
        evidence = "·".join(selected)
        title = _rotating_terms(terms["paper_titles"], index, take=1)
        paper_note = f" 교수 논문 제목 흐름({title[0]})까지 연결한다." if title else ""
        direction = str(subject.get("school_direction") or "").strip()
        addition_parts: list[str] = []
        if needs_anchors:
            addition_parts.append(f"학교별 근거는 {evidence} 흐름이다.{paper_note}")
        if needs_live:
            live_evidence = "·".join(_rotating_terms(terms["live"], index, take=2))
            addition_parts.append(f"라이브 근거는 {live_evidence} 흐름이다.")
        if needs_lens:
            _apply_lens(subject, lens)
            addition_parts.append(_lens_direction(lens))
        addition = " ".join(addition_parts)
        combined_direction = _join_sentences(direction, addition) if direction else addition
        subject["school_direction"] = _clip_text(combined_direction)
        changed = True
    return changed


def validate_gap_plan_grounding(
    content: dict[str, Any],
    profile: dict[str, Any] | None,
    *,
    student_stage: str,
) -> list[str]:
    """Require school/profile/live evidence to appear inside the actual gap plan."""
    if normalize_student_stage(student_stage) == "graduate":
        return []
    if not isinstance(content, dict) or not isinstance(profile, dict):
        return []
    subjects = _gap_subjects(content)
    if not subjects:
        return []

    errors: list[str] = []
    gap_text = " ".join(_content_text(item) for item in subjects if isinstance(item, dict))
    terms = _grounding_terms(profile)
    desired = terms["desired"]
    live = terms["live"]
    specific = terms["specific"] or terms["all"]
    lens = _school_lens(profile, terms)

    noise_hits = _term_hits(gap_text, list(_NOISE_TERMS))
    if noise_hits:
        errors.append(
            "검색 UI 찌꺼기가 리포트 본문에 노출됐다 — "
            f"{', '.join(noise_hits[:5])} 문구를 제거하고 학교/학과 근거를 사람이 읽는 문장으로 다시 써라."
        )

    label_hits = _term_hits(gap_text, list(_INTERNAL_LABELS))
    if label_hits:
        errors.append(
            "내부 작업 라벨이 리포트 본문에 노출됐다 — "
            f"{', '.join(label_hits[:5])} 같은 생성용 라벨을 제거하고 자연문장으로 다시 써라."
        )

    if desired and len(_term_hits(gap_text, desired)) < min(2, len(desired)):
        errors.append(
            "학종 DB 키워드가 세특 설계 본문에 충분히 반영되지 않았다 — "
            "strategy_section.gap_plan.subjects의 current_record/school_direction/steps/expected_effect 안에 "
            f"이 학교 정성 프로필 키워드를 2개 이상 직접 녹여라. 키워드: {', '.join(desired[:10])}"
        )

    if live and len(_term_hits(gap_text, live)) < min(2, len(live)):
        errors.append(
            "교수 논문·최신뉴스 라이브 근거가 실제 세특 설계에 들어가지 않았다 — "
            "track_section 설명만으로는 부족하다. gap_plan.subjects 각 분야의 school_direction/steps에 "
            f"라이브 근거를 연결해라. 라이브 근거: {', '.join(live[:10])}"
        )

    missing: list[str] = []
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        field = str(subject.get("field") or "분야").strip()
        subject_text = _content_text(subject)
        if specific and not _term_hits(subject_text, specific):
            missing.append(field)
        if _lens_missing(subject_text, lens):
            errors.append(
                f"{field} 분야가 학교별 관점으로 변환되지 않았다 — "
                f"'{lens['label']}' 관점에서 관찰 기준, 탐구 결과물, 설명 근거가 자연문장으로 드러나야 한다. "
                "같은 플라잉디스크/노화/도핑 소재를 쓰더라도 학교마다 제목과 탐구 설계가 달라져야 한다."
            )
    if missing:
        errors.append(
            "분야별 세특 설계가 학교별 근거 없이 일반론으로 남아 있다 — "
            f"{', '.join(missing[:6])} 분야마다 학종 DB 키워드나 교수 논문/뉴스 키워드 중 최소 1개를 "
            "school_direction 또는 steps에 직접 연결해라."
        )

    duplicate_fields = _duplicate_gap_subjects(subjects)
    if duplicate_fields:
        errors.append(
            "세특 설계가 분야만 바뀐 복붙 구조다 — "
            f"{', '.join(duplicate_fields[:6])} 분야의 school_direction/steps/expected_effect가 거의 같다. "
            "각 과목의 실제 학생 기록과 해당 학과 근거에 맞게 탐구 변수·산출물·평가축을 다르게 설계해라."
        )
    return errors


def _school_lens(profile: dict[str, Any], terms: dict[str, list[str]]) -> dict[str, str]:
    hay = " ".join(
        [
            str(profile.get("university") or ""),
            str(profile.get("department") or ""),
            str(profile.get("admission_track") or ""),
            " ".join(terms.get("all") or []),
        ]
    )
    if "체육교육" in str(profile.get("department") or ""): return {k: str(v) for k, v in _LENS_RULES[3].items() if k != "keys"}
    if any(key in str(profile.get("department") or "") for key in ("스포츠과학", "스포츠사이언스")): return {k: str(v) for k, v in _LENS_RULES[2].items() if k != "keys"}
    for rule in _LENS_RULES:
        if any(key in hay for key in rule["keys"]):
            return {k: str(v) for k, v in rule.items() if k != "keys"}
    anchor = (terms.get("specific") or terms.get("all") or ["전공적합성"])[0]
    return {
        "label": f"{anchor} 학교맞춤",
        "problem": f"학생의 기존 기록을 {anchor} 관점에서 새 질문으로 바꾼다",
        "variables": f"{anchor}와 연결되는 관찰 지표, 변화량, 비교 기준",
        "output": f"{anchor} 기반 탐구 보고서와 발표 자료",
        "defense": f"{anchor}를 선택한 이유와 학생 기록의 실제 근거",
    }

def _lens_missing(text: str, lens: dict[str, str]) -> bool:
    if lens["label"] not in text:
        return True
    if _has_forbidden_visible_text(text):
        return True
    variable_hits = _keyword_hits(text, lens["variables"])
    output_hits = _keyword_hits(text, lens["output"])
    defense_hits = _keyword_hits(text, lens["defense"])
    return len(variable_hits) < 2 or not output_hits or not defense_hits


def _apply_lens(subject: dict[str, Any], lens: dict[str, str]) -> None:
    field = str(subject.get("field") or "세특 설계").strip()
    if lens["label"] not in field:
        subject["field"] = f"{lens['label']}·{field}"
    method = _field_method(field)
    if lens["label"].startswith("스포츠산업") and any(t in field for t in ("과학", "생명")): method = ("과학 기록의 변수 설정·자료 정리 경험", "참여 사례와 간단한 설문·비교 결과", "자료 해석 기준과 운영 개선 근거")
    steps = subject.get("steps")
    if isinstance(steps, list) and steps:
        steps[0] = _clip_text(
            f"{method[0]}에서 {lens['problem']}. "
            f"관찰 기준은 다음 네 가지다: {lens['variables']}."
        )
        if len(steps) >= 2:
            steps[1] = _clip_text(
            f"{method[1]} 근거를 모아 {lens['output']}로 정리하고, "
                "결과가 예상과 다르면 기준을 바꿔 다시 비교한다."
            )
        if len(steps) >= 3:
            steps[2] = _clip_text(
                f"{method[2]}까지 남기고 한계와 다음 개선으로 정리한다. "
                f"서류 설명의 중심은 {lens['defense']}이다."
            )
    effect = str(subject.get("expected_effect") or "").strip()
    defense = (
        f"{lens['label']} 관점으로 정리하면 같은 학생 기록도 학교가 보는 평가언어로 바뀐다. "
        f"서류 설명의 중심도 {lens['defense']}이다."
    )
    combined_effect = (effect.rstrip(". ") + ". " + defense).strip() if effect else defense
    subject["expected_effect"] = _clip_text(combined_effect)


def _field_method(field: str) -> tuple[str, str, str]:
    if any(token in field for token in ("생명", "화학", "과학")):
        return ("과학 수업의 실험·관찰 기록", "측정 전후 변화와 조건 비교", "오차 원인과 실험 조건 수정")
    if any(token in field for token in ("체육", "운동")):
        return ("체육 수행 기록과 훈련 경험", "반복 수행 기록과 자세·회복 변화", "훈련 강도 조절 근거")
    if any(token in field for token in ("수학", "기하")):
        return ("수학 기록의 변화량·비교 기준", "표·그래프와 비율 계산", "계산 기준을 바꿨을 때의 차이")
    if any(token in field for token in ("사회", "윤리")):
        return ("사회 탐구의 건강권·공정성 쟁점", "사례 조사와 찬반 근거", "공동체 영향과 대안")
    return ("기존 과목 기록", "관찰 기록과 비교 자료", "학생이 바꾼 판단 기준")


def _lens_direction(lens: dict[str, str]) -> str:
    return (
        f"{lens['label']} 관점에서는 {lens['problem']}. "
        f"관찰 기준은 {lens['variables']}이고, 결과는 {lens['output']}로 정리한다."
    )


def _join_sentences(left: str, right: str) -> str:
    clean_left = str(left or "").strip()
    clean_right = str(right or "").strip()
    if not clean_left:
        return clean_right
    if not clean_right:
        return clean_left
    if clean_left[-1] not in ".!?。":
        clean_left += "."
    return f"{clean_left} {clean_right}"


def _clip_text(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _has_forbidden_visible_text(text: str) -> bool:
    return bool(_term_hits(text, list(_NOISE_TERMS)) or _term_hits(text, list(_INTERNAL_LABELS)))

def _sanitize_subject(subject: dict[str, Any]) -> None:
    for key, value in list(subject.items()):
        if isinstance(value, str):
            subject[key] = _sanitize_visible_text(value)
        elif isinstance(value, list):
            subject[key] = [_sanitize_visible_text(item) if isinstance(item, str) else item for item in value]


def _sanitize_visible_text(value: str) -> str:
    text = str(value or "")
    for label in _INTERNAL_LABELS:
        text = text.replace(label, "")
    for noise in _NOISE_TERMS:
        text = text.replace(noise, "")
    return re.sub(r"\s+", " ", text).strip(" :·,/-")


def _keyword_hits(text: str, value: str) -> list[str]:
    tokens = [token for token in re.split(r"[\s,·/]+", value) if _is_keyword_token(token)]
    return _term_hits(text, _unique(tokens))


def _is_keyword_token(token: str) -> bool:
    compact = re.sub(r"\s+", "", token)
    if _is_specific(compact):
        return True
    return bool(re.compile(r"[가-힣]").search(compact) and len(compact) >= 2 and compact not in _BROAD_TERMS)


def _gap_subjects(content: dict[str, Any]) -> list[Any]:
    strategy = content.get("strategy_section")
    if not isinstance(strategy, dict):
        return []
    gap = strategy.get("gap_plan")
    if not isinstance(gap, dict):
        return []
    subjects = gap.get("subjects")
    return subjects if isinstance(subjects, list) else []


def _grounding_terms(profile: dict[str, Any]) -> dict[str, list[str]]:
    bundle = profile.get("live_research") if isinstance(profile, dict) else None
    desired = _clean_terms(profile.get("desired_record_keywords") or [])
    live_keywords = _clean_terms(live_research_keywords(bundle, limit=10))
    paper_titles = _clean_terms(paper_titles_from_bundle(bundle, limit=3), max_len=80)
    faculty = _faculty_terms(bundle)
    news = _news_terms(bundle)
    title_terms = _title_terms(paper_titles + news)
    live = _unique(live_keywords + faculty + title_terms + paper_titles)
    all_terms = _unique(desired + live)
    specific = [term for term in all_terms if _is_specific(term)]
    return {
        "desired": desired,
        "live": live,
        "paper_titles": paper_titles,
        "all": all_terms,
        "specific": specific,
    }


def _faculty_terms(bundle: Any) -> list[str]:
    if not isinstance(bundle, dict):
        return []
    terms: list[str] = []
    for profile in bundle.get("faculty_profiles") or []:
        if isinstance(profile, dict):
            terms.extend([profile.get("major"), profile.get("department")])
    return _clean_terms(terms)


def _news_terms(bundle: Any) -> list[str]:
    if not isinstance(bundle, dict):
        return []
    terms: list[str] = []
    for item in bundle.get("field_news_live_probe") or []:
        if isinstance(item, dict):
            terms.extend(item.get("keywords") or [])
            terms.append(item.get("title"))
    return _clean_terms(terms, max_len=80)


def _title_terms(values: list[str]) -> list[str]:
    domain = ("운동", "스포츠", "체육", "재활", "생리", "역학", "건강", "트레이닝", "손상", "부상", "도핑", "노화", "기능", "처방", "측정")
    terms: list[str] = []
    for value in values:
        for token in re.findall(r"[가-힣A-Za-z0-9]{3,}", value):
            clean = re.sub(r"(은|는|이|가|을|를|과|와|의|으로|에서|에게|부터|까지|입니다)$", "", token)
            if _is_specific(clean) and any(key in clean for key in domain):
                terms.append(clean)
    return _unique(terms)


def _clean_terms(values: Any, *, max_len: int = 32) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).replace("AI", "데이터 활용").strip(" ·,/-")
        if not text or len(text) > max_len or any(noise in text for noise in _NOISE_TERMS):
            continue
        if text not in out:
            out.append(text)
    return out


def _is_specific(term: str) -> bool:
    compact = re.sub(r"\s+", "", term)
    return len(compact) >= 3 and compact.lower() not in _BROAD_TERMS


def _term_hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def _rotating_terms(terms: list[str], index: int, *, take: int) -> list[str]:
    if not terms:
        return []
    return [terms[(index + offset) % len(terms)] for offset in range(min(take, len(terms)))]


def _duplicate_gap_subjects(subjects: list[Any]) -> list[str]:
    seen: dict[str, str] = {}
    duplicated: list[str] = []
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        field = str(subject.get("field") or "분야").strip()
        body = " ".join(
            [
                str(subject.get("school_direction") or ""),
                " ".join(str(step) for step in subject.get("steps") or []),
                str(subject.get("expected_effect") or ""),
            ]
        )
        key = re.sub(r"\s+", "", body)
        key = re.sub(r"[가-힣A-Za-z]+분야|[가-힣A-Za-z]+과목|[가-힣A-Za-z]+세특", "", key)
        key = key[:220]
        if len(key) < 80:
            continue
        if key in seen:
            duplicated.extend([seen[key], field])
        else:
            seen[key] = field
    return _unique(duplicated)


def _content_text(obj: Any) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj)
    return " ".join(parts)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out
