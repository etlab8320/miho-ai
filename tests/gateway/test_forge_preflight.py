from pathlib import Path

from gateway.forge_preflight import (
    TARGET_PROJECT_QUESTION,
    project_target_question_for,
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
