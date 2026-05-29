import json

import gateway.generated_media as generated_media
from gateway.generated_media import append_missing_generated_media_directives


def _tool_message(content, tool_name="image_generate"):
    return {
        "role": "tool",
        "tool_name": tool_name,
        "content": content,
    }


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


def test_ignores_bare_local_paths_outside_generated_media_roots(tmp_path):
    image = tmp_path / "private.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = append_missing_generated_media_directives(
        "완료",
        [_tool_message(f"created {image}", "terminal")],
    )

    assert response == "완료"
