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


def test_gateway_allows_explicit_new_project_target():
    text = "새 프로젝트 /Users/etlab/projects/diary-app 에 다이어리 만들어줘"

    assert project_target_question_for(text) is None


def test_gateway_does_not_block_image_artifact_requests():
    assert project_target_question_for("오늘 한화 경기 리뷰 이미지 만들어줘") is None
