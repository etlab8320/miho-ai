"""HTML-first report shell for sports performance PDFs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jinja2
from markupsafe import Markup

from miho_constants import get_miho_home
from plugins.academy_ops.brand_assets import academy_brand_logo_src
from plugins.academy_ops.report_fonts import report_font_css
from plugins.academy_ops.student_card_fonts import goyang_font_css

from .exercise_library import exercise_library_entries
from .prescription_engine import build_personalized_prescription
from .report_contracts import allow_placeholders, runtime_report_contract
from .report_templates import build_report_template_response
from .variable_compare import display_measure, display_unit

_KST = ZoneInfo("Asia/Seoul")
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "sports_motion_report_shell.html"
_MEDIA_DIR_NAME = "sports_performance_reports"
_DESIGN_REFERENCE = {
    "name": "MAX performance data report",
    "source": "https://github.com/shadcn-ui/ui",
    "notes": [
        "CSS 변수와 OKLCH 토큰으로 색을 통제한다.",
        "카드 장식보다 데이터 표, 배지, 섹션 밴드 중심으로 구성한다.",
        "복사 가능한 UI 철학만 참고하고 기존 입시 PDF 템플릿 색/구조는 재사용하지 않는다.",
    ],
}
_DIRECTION_LABELS = {
    "higher_is_better": "높을수록 좋음",
    "lower_is_better": "낮을수록 좋음",
    "range_is_better": "목표 범위가 좋음",
    "faster_is_better": "빠를수록 좋음",
    "higher_with_horizontal_balance": "높되 수평속도 균형 필요",
    "lower_with_control_is_better": "짧되 제어 필요",
    "higher_with_control": "높되 착지 제어 필요",
    "sequence_is_better": "순서가 맞아야 좋음",
}
_PLAIN_VARIABLE_LABELS = {
    "takeoff_angle": "뛰어오르는 각도",
    "horizontal_velocity": "앞으로 나가는 속도",
    "vertical_velocity": "위로 뜨는 힘",
    "takeoff_transition_time": "앉았다 밀고 나가기까지 걸린 시간",
    "descent_velocity": "앉는 속도",
    "com_descent_distance": "얼마나 깊게 앉았는지",
    "hip_peak_angular_velocity": "엉덩이를 펴는 빠르기",
    "knee_peak_angular_velocity": "무릎을 펴는 빠르기",
    "ankle_peak_angular_velocity": "발목으로 미는 빠르기",
    "hip_takeoff_angle": "엉덩이가 펴진 정도",
    "knee_takeoff_angle": "무릎이 펴진 정도",
    "ankle_takeoff_angle": "발목으로 민 각도",
    "arm_backswing_angle": "팔을 뒤로 준비한 크기",
    "arm_swing_peak_velocity": "팔을 앞으로 흔드는 빠르기",
    "com_foot_distance": "착지 때 발을 앞으로 뻗은 거리",
    "flight_hip_min_angle": "공중에서 다리를 당긴 정도",
    "flight_knee_min_angle": "착지 전 무릎을 접은 정도",
    "contact_time": "발이 바닥에 머문 시간",
    "turn_angle": "방향을 바꾸는 각도",
    "deceleration_distance": "멈추는 데 걸린 거리",
    "trunk_lean": "상체를 낮춘 정도",
    "first_step_projection": "첫걸음이 앞으로 나간 정도",
    "foot_contact_timing": "발을 딛고 떼는 타이밍",
    "release_angle": "공을 놓는 각도",
    "release_height": "공을 놓는 높이",
    "trunk_rotation": "몸통을 돌린 정도",
    "hip_extension": "엉덩이를 펴는 힘",
    "sequence_timing": "다리-몸통-팔이 이어지는 순서",
}
_PLAIN_VARIABLE_ROLES = {
    "takeoff_angle": "점프가 너무 위로만 뜨거나 너무 낮게 나가는지 본다.",
    "horizontal_velocity": "몸이 앞으로 얼마나 빠르게 나가는지 본다.",
    "vertical_velocity": "몸이 위로 얼마나 떠오르는지 본다.",
    "takeoff_transition_time": "앉은 뒤 점프를 시작하기까지 늦는지 본다.",
    "descent_velocity": "앉는 동작이 너무 느린지 본다.",
    "com_descent_distance": "너무 깊게 앉거나 너무 얕게 앉는지 본다.",
    "hip_peak_angular_velocity": "엉덩이와 허벅지 뒤쪽 힘이 빠르게 쓰이는지 본다.",
    "knee_peak_angular_velocity": "무릎을 펴는 힘이 빠르게 나오는지 본다.",
    "ankle_peak_angular_velocity": "마지막에 발목으로 바닥을 잘 미는지 본다.",
    "hip_takeoff_angle": "점프 순간 엉덩이가 충분히 펴지는지 본다.",
    "knee_takeoff_angle": "점프 순간 무릎이 충분히 펴지는지 본다.",
    "ankle_takeoff_angle": "점프 순간 발목으로 끝까지 밀었는지 본다.",
    "arm_backswing_angle": "점프 전 팔을 뒤로 잘 준비했는지 본다.",
    "arm_swing_peak_velocity": "팔을 앞으로 빠르게 가져오는지 본다.",
    "com_foot_distance": "착지 때 발을 앞으로 잘 뻗는지 본다.",
    "flight_hip_min_angle": "공중에서 다리를 잘 당기는지 본다.",
    "flight_knee_min_angle": "착지 전 무릎을 잘 접는지 본다.",
    "contact_time": "방향을 바꿀 때 발이 바닥에 오래 머무는지 본다.",
    "turn_angle": "몸이 다음 방향으로 잘 돌아서는지 본다.",
    "deceleration_distance": "멈추는 데 거리가 너무 길어지는지 본다.",
    "trunk_lean": "방향전환 때 상체를 낮게 유지하는지 본다.",
    "first_step_projection": "돌아선 뒤 첫걸음이 앞으로 잘 나가는지 본다.",
    "foot_contact_timing": "발을 딛고 떼는 타이밍이 늦지 않은지 본다.",
    "release_angle": "공을 너무 높게 또는 너무 낮게 놓는지 본다.",
    "release_height": "공을 놓는 위치가 충분히 높은지 본다.",
    "trunk_rotation": "몸통 회전이 공에 잘 전달되는지 본다.",
    "hip_extension": "엉덩이와 하체 힘이 던지기에 들어가는지 본다.",
    "sequence_timing": "다리, 몸통, 팔이 순서대로 이어지는지 본다.",
}
_PLAIN_TARGET_LABELS = {
    "takeoff_result": "뛰어오르는 각도와 속도",
    "horizontal_velocity_loss": "앞으로 나가는 속도 유지",
    "transition_speed": "앉았다 바로 미는 속도",
    "hip_drive": "엉덩이와 허벅지 뒤쪽 힘",
    "arm_swing": "팔 흔드는 타이밍",
    "landing_efficiency": "착지 때 기록 손실 줄이기",
    "contact_time": "발을 짧게 딛기",
    "deceleration_control": "짧게 멈추기",
    "trunk_lean": "낮은 자세 유지",
    "reacceleration": "돌자마자 다시 뛰기",
    "release_angle": "공을 놓는 각도",
    "release_height": "공을 놓는 높이",
    "trunk_rotation": "몸통 회전",
    "sequence_timing": "다리-몸통-팔 순서",
}


def sports_report_html_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    try:
        result = write_sports_report_html(args or {})
    except (OSError, RuntimeError, jinja2.TemplateError) as exc:
        result = {"ok": False, "errors": [f"운동분석 HTML 템플릿 생성 실패: {exc}"]}
    return json.dumps(result, ensure_ascii=False)


def write_sports_report_html(args: dict[str, Any]) -> dict[str, Any]:
    payload = build_sports_report_html_payload(args)
    if not payload["ok"]:
        return payload
    contract = runtime_report_contract(args, payload)
    if not contract["ok"]:
        return contract

    html = render_sports_report_html(args)
    out_dir = get_miho_home() / "media_cache" / _MEDIA_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(
        payload["student"]["name"],
        payload["exercise"]["label"],
        "운동분석리포트",
    )
    html_path = _unique_path(out_dir / f"{stem}.html")
    html_path.write_text(html, encoding="utf-8")
    return {
        "ok": True,
        "template_key": payload["template_key"],
        "html_path": str(html_path),
        "message": "운동분석 HTML 생성 완료. PDF 변환과 품질검증 후 첨부해야 한다.",
        "next_action": "run_html_pdf_quality_gate",
        "design_reference": _DESIGN_REFERENCE,
    }


def render_sports_report_html(args: dict[str, Any] | None = None) -> str:
    report = build_sports_report_html_payload(args or {})
    if not report["ok"]:
        raise RuntimeError("지원하지 않는 종목이라 HTML 리포트를 만들 수 없다.")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(_TEMPLATE_PATH.parent),
        autoescape=jinja2.select_autoescape(["html"]),
        undefined=jinja2.ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(_TEMPLATE_PATH.name)
    return template.render(
        font_css=Markup(report_font_css() + goyang_font_css()),
        logo_src=academy_brand_logo_src() or "",
        report=report,
    )


def build_sports_report_html_payload(args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    response = build_report_template_response({"exercise": args.get("exercise") or "제멀"})
    if not response.get("ok"):
        return {
            "ok": False,
            "errors": response.get("errors") or ["현재 지원하지 않는 종목이다."],
        }

    template = response["template"]
    exercise = response["exercise"]
    placeholders_allowed = allow_placeholders(args)
    variables_by_key = _input_variables_by_key(_variable_inputs(args))
    variable_groups = _variable_groups(template, variables_by_key, allow_placeholders=placeholders_allowed)
    variable_labels = _variable_labels(variable_groups)
    base_training_program = _training_program(template["training_program"], variable_labels)
    prescription = build_personalized_prescription(
        variable_groups=variable_groups,
        training_program=base_training_program,
        target_labeler=_plain_target_label,
    )
    record = _record(args.get("record"), allow_placeholders=placeholders_allowed)

    template_key = f"{exercise['key']}_motion_report_v1"
    return {
        "ok": True,
        "template_key": template_key,
        "generated_at": datetime.now(_KST).strftime("%Y-%m-%d %H:%M"),
        "design_reference": _DESIGN_REFERENCE,
        "student": _student(args.get("student")),
        "exercise": {"key": exercise["key"], "label": exercise["name_ko"]},
        "record": record,
        "summary_metrics": _summary_metrics(record),
        "comparison_summary": _comparison_summary(args.get("comparison"), allow_placeholders=placeholders_allowed),
        "variable_groups": prescription["variable_groups"],
        "strengths": prescription["strengths"],
        "bottlenecks": _bottlenecks(args.get("bottlenecks"), prescription["variable_groups"])
        if args.get("bottlenecks")
        else prescription["bottlenecks"],
        "training_program": prescription["training_program"],
        "variable_exercise_map": _variable_exercise_map(exercise["key"], prescription["variable_groups"]),
        "evidence": _evidence_rows(template["reference_groups"]),
        "llm_validation": template["llm_validation_contract"],
        "review_contract": template["review_contract"],
    }


def _student(raw: Any) -> dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "name": str(data.get("name") or data.get("student_name") or "학생").strip() or "학생",
        "gender": str(data.get("gender") or "성별 미입력").strip(),
        "academy": str(data.get("academy") or data.get("branch") or "소속 미입력").strip(),
        "measured_at": str(data.get("measured_at") or "측정일 미입력").strip(),
    }


def _record(raw: Any, *, allow_placeholders: bool) -> dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    empty_current = "측정 대기" if allow_placeholders else "최근 기록 재조회 필요"
    empty_previous = "이전 기록 대기" if allow_placeholders else "이전 기록 없음"
    empty_percentile = "전국 모델 계산 대기" if allow_placeholders else "전국 모델 재계산 필요"
    empty_change = "변화량 대기" if allow_placeholders else "변화량 미산출"
    return {
        "current": str(data.get("current") or data.get("latest") or empty_current).strip(),
        "previous": str(data.get("previous") or empty_previous).strip(),
        "change": str(data.get("change") or empty_change).strip(),
        "percentile": str(data.get("percentile") or empty_percentile).strip(),
    }


def _summary_metrics(record: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"kind": "record", "label": "최신 기록", "value": record["current"], "note": "MAX API 최근 측정값"},
        {"kind": "change", "label": "이전 대비", "value": record["change"], "note": "학생 본인 직전 기록과 비교"},
        {"kind": "model", "label": "전국 모델", "value": record["percentile"], "note": "성별 상위권 모델과 비교"},
    ]


def _comparison_summary(raw: Any, *, allow_placeholders: bool) -> list[dict[str, str]]:
    if isinstance(raw, list) and raw:
        return [_string_map(item) for item in raw if isinstance(item, dict)]
    if not allow_placeholders:
        return [
            {"label": "전국 성별 상위 1%", "value": "전국 모델 재계산 필요", "note": "MAX API 전국 모델 재조회 필요"},
            {"label": "전국 성별 상위 5%", "value": "전국 모델 재계산 필요", "note": "지점별 상위 비교는 사용하지 않음"},
            {"label": "학생 직전 기록", "value": "이전 기록 없음", "note": "개인 변화량은 다음 측정부터 계산"},
        ]
    return [
        {"label": "전국 성별 상위 1%", "value": "상위 모델 산출 대기", "note": "주간 SQLite 스냅샷 기준"},
        {"label": "전국 성별 상위 5%", "value": "상위 모델 산출 대기", "note": "지점별 상위 비교는 사용하지 않음"},
        {"label": "학생 직전 기록", "value": "이전 기록 대기", "note": "개인 변화량과 함께 해석"},
    ]


def _variable_inputs(args: dict[str, Any]) -> Any:
    for key in ("variables", "motion_variables"):
        if isinstance(args.get(key), list):
            return args[key]
    records = args.get("records")
    if isinstance(records, list):
        return records
    max_analysis = args.get("max_analysis")
    if isinstance(max_analysis, dict):
        context = max_analysis.get("llm_context") if isinstance(max_analysis.get("llm_context"), dict) else {}
        latest_variables = context.get("latest_session_variables")
        if isinstance(latest_variables, list) and latest_variables:
            return latest_variables
        for key in ("records", "variables"):
            if isinstance(max_analysis.get(key), list):
                return max_analysis[key]
    return []


def _input_variables_by_key(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, list):
        return {}
    rows: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("variable_key") or "").strip()
        if key:
            rows[key] = _normalized_variable_row(item)
    return rows


def _variable_groups(
    template: dict[str, Any],
    variables_by_key: dict[str, dict[str, str]],
    *,
    allow_placeholders: bool,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group in template["variable_groups"]:
        variables = []
        for variable in group["variables"]:
            measured = variables_by_key.get(variable["key"], {})
            if not allow_placeholders and not _has_number(str(measured.get("current") or "")):
                continue
            variables.append(
                {
                    **variable,
                    "display_name": _plain_variable_label(variable),
                    "display_role": _plain_variable_role(variable),
                    "direction_label": _DIRECTION_LABELS.get(variable["direction"], variable["direction"]),
                    "current": measured.get("current", "측정 대기"),
                    "previous": measured.get("previous", "-"),
                    "elite_1pct": measured.get(
                        "elite_1pct",
                        "전국 상위 1% 모델 대기" if allow_placeholders else "전국 모델 재계산 필요",
                    ),
                    "gap": measured.get("gap", "계산 대기" if allow_placeholders else "계산 재실행 필요"),
                    "status": measured.get("status", "후검증 대기" if allow_placeholders else "MAX API 측정값"),
                }
            )
        if variables or allow_placeholders:
            groups.append({**group, "variables": variables})
    return groups


def _variable_labels(variable_groups: list[dict[str, Any]]) -> dict[str, str]:
    return {
        variable["key"]: variable["display_name"]
        for group in variable_groups
        for variable in group["variables"]
    }


def _bottlenecks(raw: Any, variable_groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(raw, list) and raw:
        return [_string_map(item) for item in raw if isinstance(item, dict)]
    rows = [variable for group in variable_groups for variable in group["variables"]]
    return [
        {
            "title": variable["display_name"],
            "target": ", ".join(_plain_target_label(target) for target in variable["prescription_targets"]),
            "why": variable["display_role"],
            "direction": variable["direction_label"],
        }
        for variable in rows[:3]
    ]


def _training_program(raw: dict[str, Any], variable_labels: dict[str, str]) -> dict[str, Any]:
    blocks = []
    for block in raw.get("exercise_blocks", []):
        effects = block.get("expected_variable_effects", [])
        primary_labels = [_label_for_key(key, variable_labels) for key in block["primary_variables"]]
        secondary_labels = [_label_for_key(key, variable_labels) for key in block["secondary_variables"]]
        blocks.append(
            {
                **block,
                "primary_variable_labels": primary_labels,
                "secondary_variable_labels": secondary_labels,
                "effect_summary": ", ".join(_label_for_key(effect["variable_key"], variable_labels) for effect in effects),
            }
        )
    return {**raw, "exercise_blocks": blocks}


def _variable_exercise_map(exercise_key: str, variable_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    library = exercise_library_entries(exercise_key)
    fallback = library[:3]
    rows: list[dict[str, Any]] = []
    for group in variable_groups:
        for variable in group.get("variables") or []:
            key = str(variable.get("key") or "")
            if not key:
                continue
            linked = _linked_exercises_for_variable(key, library)
            if len(linked) < 3:
                linked.extend(item for item in fallback if item not in linked)
            rows.append(
                {
                    "phase": f"P{group.get('priority')} · {group.get('title')}",
                    "variable": variable.get("display_name") or variable.get("key") or key,
                    "evaluation": variable.get("evaluation_label") or variable.get("status") or "판정",
                    "exercises": [_exercise_link_row(item) for item in linked[:3]],
                }
            )
    return rows


def _linked_exercises_for_variable(key: str, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(item: dict[str, Any]) -> int:
        primary = [str(value) for value in item.get("primary_variables") or []]
        secondary = [str(value) for value in item.get("secondary_variables") or []]
        if key in primary:
            return 3
        if key in secondary:
            return 2
        return 0

    ranked = [(score(item), index, item) for index, item in enumerate(library)]
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for item_score, _, item in ranked if item_score > 0]


def _exercise_link_row(item: dict[str, Any]) -> dict[str, str]:
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    dosage = item.get("dosage") if isinstance(item.get("dosage"), dict) else {}
    video_map: dict[str, Any] = video if isinstance(video, dict) else {}
    dosage_map: dict[str, Any] = dosage if isinstance(dosage, dict) else {}
    return {
        "title": str(item.get("title") or "운동"),
        "kind_label": str(item.get("kind_label") or ""),
        "url": str(video_map.get("url") or ""),
        "why": str(item.get("how_to") or item.get("target") or ""),
        "dose": " · ".join(str(value) for value in (dosage_map.get("sets"), dosage_map.get("reps_or_time"), dosage_map.get("load")) if value),
    }


def _plain_variable_label(variable: dict[str, Any]) -> str:
    key = str(variable.get("key") or "")
    return _PLAIN_VARIABLE_LABELS.get(key) or str(variable.get("name") or key)


def _plain_variable_role(variable: dict[str, Any]) -> str:
    key = str(variable.get("key") or "")
    return _PLAIN_VARIABLE_ROLES.get(key) or str(variable.get("role") or "")


def _label_for_key(key: Any, variable_labels: dict[str, str]) -> str:
    text = str(key or "")
    return variable_labels.get(text) or _PLAIN_VARIABLE_LABELS.get(text) or text.replace("_", " ")


def _plain_target_label(key: Any) -> str:
    text = str(key or "")
    return _PLAIN_TARGET_LABELS.get(text) or text.replace("_", " ")


def _evidence_rows(reference_groups: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group_key, refs in reference_groups.items():
        for ref in refs:
            rows.append({"group": group_key, **ref})
    return rows


def _string_map(item: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in item.items()}


def _normalized_variable_row(item: dict[str, Any]) -> dict[str, str]:
    row = _string_map(item)
    key = str(item.get("key") or item.get("variable_key") or "")
    current = item.get("current")
    if current is None:
        current = item.get("value", item.get("variable_value"))
    if current is not None:
        unit = str(item.get("unit") or row.get("unit") or "").strip()
        row["current"] = display_measure(key, current, unit)
    if item.get("elite_1pct") is not None:
        row["elite_1pct"] = display_measure(key, item.get("elite_1pct"), row.get("unit") or display_unit(item.get("elite_1pct")))
    if "measured_at" in item and "status" not in row:
        row["status"] = f"{item['measured_at']} 측정"
    return row


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _safe_stem(*parts: str) -> str:
    raw = "_".join(part.strip() for part in parts if part and part.strip())
    clean = re.sub(r"[^\w가-힣.-]+", "_", raw, flags=re.UNICODE).strip("_.")
    return clean[:120] or "sports_report"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
