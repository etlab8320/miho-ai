import json

import gateway.generated_media as generated_media
from gateway.generated_media import append_missing_generated_media_directives


def _tool_message(content, tool_name="image_generate"):
    return {
        "role": "tool",
        "tool_name": tool_name,
        "content": content,
    }


def _user_message(content):
    return {"role": "user", "content": content}


def test_appends_image_generate_url_when_final_text_omits_it():
    result = json.dumps({
        "success": True,
        "image": "https://fal.media/generated.png",
    })

    response = append_missing_generated_media_directives(
        "완성했어.",
        [_tool_message(result)],
    )

    assert "완성했어." in response
    assert "![generated image](https://fal.media/generated.png)" in response


def test_appends_image_generate_local_path_as_media_directive():
    result = json.dumps({
        "success": True,
        "image": "/tmp/miho-cache/chart.png",
    })

    response = append_missing_generated_media_directives(
        "완성했어.",
        [_tool_message(result)],
    )

    assert response.endswith("MEDIA:/tmp/miho-cache/chart.png")


def test_does_not_duplicate_image_already_in_final_text():
    result = json.dumps({
        "success": True,
        "image": "https://fal.media/generated.png",
    })
    final = "여기 있어: ![표](https://fal.media/generated.png)"

    response = append_missing_generated_media_directives(final, [_tool_message(result)])

    assert response == final


def test_preserves_existing_tts_media_tag_promotion():
    response = append_missing_generated_media_directives(
        "완료",
        [_tool_message("[[audio_as_voice]]\nMEDIA:/tmp/speech.ogg", "tts")],
    )

    assert response.endswith("[[audio_as_voice]]\nMEDIA:/tmp/speech.ogg")


def test_appends_academy_consultation_candidate_media_when_final_text_omits_it():
    result = json.dumps(
        {
            "ok": True,
            "operation": "consultation.candidates",
            "message": "상담 후보 5명\nMEDIA:/tmp/consultation-candidates.png",
            "media_tag": "MEDIA:/tmp/consultation-candidates.png",
        },
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "상담 후보 목록 만들었어.",
        [_tool_message(result, "academy_consultation_candidates")],
    )

    assert response.endswith("MEDIA:/tmp/consultation-candidates.png")


def test_only_promotes_current_turn_tool_media(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    old_image = miho_home / "cache" / "media" / "academy_consultation_candidates" / "old.png"
    current_image = miho_home / "cache" / "media" / "academy_consultation_candidates" / "current.png"
    old_image.parent.mkdir(parents=True)
    old_image.write_bytes(b"old")
    current_image.write_bytes(b"current")
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", miho_home / "cache" / "media" / "gateway_promoted")
    old_result = json.dumps(
        {"ok": True, "message": f"예전 이미지\nMEDIA:{old_image}", "media_tag": f"MEDIA:{old_image}"},
        ensure_ascii=False,
    )
    current_result = json.dumps(
        {"ok": True, "message": f"현재 이미지\nMEDIA:{current_image}", "media_tag": f"MEDIA:{current_image}"},
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "상담 후보 5명 만들었어.",
        [
            _tool_message(old_result, "academy_consultation_candidates"),
            _user_message("5명 줘~"),
            _tool_message(current_result, "academy_consultation_candidates"),
        ],
    )

    assert f"MEDIA:{current_image}" in response
    assert f"MEDIA:{old_image}" not in response


def test_appends_generated_discord_export_image_path_from_tool_output(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    image = miho_home / "discord_exports" / "attendance_2026-05-29_table.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    promoted_dir = miho_home / "cache" / "media" / "gateway_promoted"
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", promoted_dir)
    tool_output = json.dumps({"path": str(image), "status": "created"}, ensure_ascii=False)

    response = append_missing_generated_media_directives(
        "이미지로 바로 뽑아놨어. 첨부:",
        [_tool_message(tool_output, "terminal")],
    )

    promoted = promoted_dir / image.name
    assert response.endswith(f"MEDIA:{promoted}")
    assert promoted.read_bytes() == b"\x89PNG\r\n\x1a\n"


def test_removes_dangling_attachment_label_when_appending_media():
    result = json.dumps(
        {
            "ok": True,
            "message": "상담 후보 5명\nMEDIA:/tmp/consultation-candidates.png",
            "media_tag": "MEDIA:/tmp/consultation-candidates.png",
        },
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "상담 후보 5명 만들었어.\n\n첨부:",
        [_tool_message(result, "academy_consultation_candidates")],
    )

    assert "첨부:" not in response
    assert response.endswith("MEDIA:/tmp/consultation-candidates.png")


def test_ignores_media_paths_inside_current_turn_read_file_output(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    old_image = miho_home / "cache" / "media" / "academy_attendance_days" / "old.png"
    old_image.parent.mkdir(parents=True)
    old_image.write_bytes(b"old")
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", miho_home / "cache" / "media" / "gateway_promoted")
    tool_output = json.dumps(
        {
            "content": f"과거 답변: MEDIA:{old_image}\n또 다른 경로 {old_image}",
            "total_lines": 1,
        },
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "남학생 평균 267.8cm, 여학생 평균 216.3cm",
        [_user_message("남여 제멀 평균 기록 부탁해"), _tool_message(tool_output, "read_file")],
    )

    assert response == "남학생 평균 267.8cm, 여학생 평균 216.3cm"


def test_ignores_media_paths_inside_current_turn_execute_code_output(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    old_image = miho_home / "cache" / "media" / "gateway_promoted" / "old.png"
    old_image.parent.mkdir(parents=True)
    old_image.write_bytes(b"old")
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", miho_home / "cache" / "media" / "gateway_promoted")
    tool_output = json.dumps(
        {"status": "success", "output": f"debug output includes {old_image}"},
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "평균 계산 완료",
        [_user_message("평균 기록 부탁해"), _tool_message(tool_output, "execute_code")],
    )

    assert response == "평균 계산 완료"


def test_ignores_bare_local_paths_outside_generated_media_roots(tmp_path):
    image = tmp_path / "private.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = append_missing_generated_media_directives(
        "완료",
        [_tool_message(f"created {image}", "terminal")],
    )

    assert response == "완료"


def test_appends_health_card_png_from_media_cache_when_final_text_omits_it(tmp_path, monkeypatch):
    # The health-report skill renders its PNG under media_cache/ and tells the
    # model to attach it with a MEDIA: line. When the model forgets, a structured
    # path the skill exposed must still be promoted so the image ships turn 1.
    miho_home = tmp_path / ".miho"
    image = miho_home / "media_cache" / "health-nightly" / "2026-05-31-health-card.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    promoted_dir = miho_home / "cache" / "media" / "gateway_promoted"
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", promoted_dir)
    tool_output = json.dumps({"path": str(image), "status": "created"}, ensure_ascii=False)

    response = append_missing_generated_media_directives(
        "주간 건강 리포트야.",
        [_tool_message(tool_output, "terminal")],
    )

    promoted = promoted_dir / image.name
    assert response.endswith(f"MEDIA:{promoted}")
    assert promoted.read_bytes() == b"\x89PNG\r\n\x1a\n"


def test_does_not_duplicate_media_already_present_from_structured_tool_output(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    image = miho_home / "media_cache" / "academy_reports" / "assignment.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    promoted_dir = miho_home / "cache" / "media" / "gateway_promoted"
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", promoted_dir)
    tool_output = json.dumps(
        {
            "ok": True,
            "message": f"보고서야. MEDIA:{image}",
            "image_path": str(image),
            "media_tag": f"MEDIA:{image}",
        },
        ensure_ascii=False,
    )
    final = f"정리했어.\nMEDIA:{image}"

    response = append_missing_generated_media_directives(
        final,
        [_user_message("이미지로 줘"), _tool_message(tool_output, "academy_report_image")],
    )

    assert response == final
    assert not (promoted_dir / image.name).exists()


def test_does_not_duplicate_original_when_promoted_copy_is_already_present(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    image = miho_home / "media_cache" / "academy_reports" / "assignment.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\nsame")
    promoted_dir = miho_home / "cache" / "media" / "gateway_promoted"
    promoted_dir.mkdir(parents=True)
    promoted = promoted_dir / image.name
    promoted.write_bytes(image.read_bytes())
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", promoted_dir)
    tool_output = json.dumps(
        {
            "ok": True,
            "message": f"보고서야. MEDIA:{image}",
            "image_path": str(image),
            "media_tag": f"MEDIA:{image}",
        },
        ensure_ascii=False,
    )
    final = f"정리했어.\nMEDIA:{promoted}"

    response = append_missing_generated_media_directives(
        final,
        [_user_message("이미지로 줘"), _tool_message(tool_output, "academy_report_image")],
    )

    assert response == final


def test_ignores_media_cache_path_in_stdout_text_not_structured(tmp_path, monkeypatch):
    # A media_cache path appearing only in stdout text (not a structured path
    # key) is still ignored — same policy as read_file/execute_code, so the new
    # safe-root does not start scraping debug output for paths.
    miho_home = tmp_path / ".miho"
    image = miho_home / "media_cache" / "health-nightly" / "old.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"old")
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", miho_home / "cache" / "media" / "gateway_promoted")
    tool_output = json.dumps(
        {"status": "success", "output": f"saved chart to {image}"},
        ensure_ascii=False,
    )

    response = append_missing_generated_media_directives(
        "완료",
        [_user_message("리포트 줘"), _tool_message(tool_output, "execute_code")],
    )

    assert response == "완료"
