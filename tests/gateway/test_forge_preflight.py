import json
from pathlib import Path

from gateway.forge_preflight import (
    TARGET_PROJECT_QUESTION,
    project_target_question_for,
)
from gateway.preflight_learning import (
    consume_preflight_correction,
    is_conversation_correction,
    remember_preflight_prompt,
)


def test_gateway_blocks_ambiguous_diary_build_before_agent_runs():
    assert project_target_question_for("다이어리 만들어줘") == TARGET_PROJECT_QUESTION


def test_gateway_blocks_ambiguous_academy_consultation_feature():
    assert project_target_question_for("학원 상담 기능 좀 만들어줘") == TARGET_PROJECT_QUESTION


def test_gateway_allows_explicit_existing_project_target():
    assert project_target_question_for("AcademyOS에 다이어리 만들어줘") is None


def test_gateway_allows_generic_named_project_target():
    assert project_target_question_for("some-project에 api 추가해줘") is None


def test_gateway_allows_explicit_new_project_target():
    text = "새 프로젝트 /Users/etlab/projects/diary-app 에 다이어리 만들어줘"

    assert project_target_question_for(text) is None


def test_gateway_does_not_block_image_artifact_requests():
    assert project_target_question_for("오늘 한화 경기 리뷰 이미지 만들어줘") is None


def test_gateway_does_not_block_general_app_conversation():
    text = (
        "오호... 근데 apk도 사실 한몫해 ㅋㅋ 커스텀 앱 만들어서 쓸때 "
        "이것만한게 없어서 아무리 웹을 앱처럼 알림기능 추가한다고 해도, "
        "네이티브앱 성능은 못따라가니깐 ㅋ"
    )

    assert project_target_question_for(text) is None


def test_gateway_still_blocks_direct_custom_app_build_request():
    assert project_target_question_for("커스텀 앱 만들어줘") == TARGET_PROJECT_QUESTION


def test_gateway_does_not_block_capability_questions_about_apps():
    assert project_target_question_for("아이폰이랑 에이닷 앱이 돼?") is None


def test_gateway_preflight_has_no_specific_project_allowlist():
    source = Path("gateway/forge_preflight.py").read_text(encoding="utf-8").lower()

    assert "academyos" not in source
    assert "teamimax" not in source
    assert "maxtest" not in source


def test_preflight_learning_records_conversation_false_positive(tmp_path):
    pending = {}
    session_key = "agent:main:discord:group:123"
    remember_preflight_prompt(
        pending,
        session_key,
        original_text="커스텀 앱 만들어서 쓸때 이게 편하긴 해",
        question=TARGET_PROJECT_QUESTION,
        platform="discord",
    )

    assert is_conversation_correction("아니 대화야") is True
    assert consume_preflight_correction(
        pending,
        session_key,
        correction_text="아니 대화야",
        home=tmp_path,
    ) is True

    assert pending == {}
    queue_path = tmp_path / "review" / "preflight_false_positives.jsonl"
    record = json.loads(queue_path.read_text(encoding="utf-8").strip())
    assert record["kind"] == "forge_preflight_false_positive"
    assert record["platform"] == "discord"
    assert record["original_text"] == "커스텀 앱 만들어서 쓸때 이게 편하긴 해"
    assert record["correction_text"] == "아니 대화야"


def test_preflight_learning_ignores_normal_followup(tmp_path):
    pending = {}
    session_key = "agent:main:discord:group:123"
    remember_preflight_prompt(
        pending,
        session_key,
        original_text="커스텀 앱 만들어줘",
        question=TARGET_PROJECT_QUESTION,
        platform="discord",
    )

    assert consume_preflight_correction(
        pending,
        session_key,
        correction_text="새 프로젝트 /Users/etlab/projects/custom-app",
        home=tmp_path,
    ) is False
    assert session_key in pending
    assert not (tmp_path / "review" / "preflight_false_positives.jsonl").exists()
