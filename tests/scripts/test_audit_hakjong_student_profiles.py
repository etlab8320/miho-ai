from __future__ import annotations

from scripts.audit_hakjong_student_profiles import clip


def test_clip_removes_hakjong_banned_practical_word() -> None:
    assert "실기" not in clip("희망분야: [실기] 스포츠과학부")
    assert "수행" in clip("희망분야: [실기] 스포츠과학부")
