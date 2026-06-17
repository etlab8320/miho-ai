"""Tests for practical reco score recalculation guards."""

from __future__ import annotations

from plugins.academy_ops.practical_reco_recalc import validate_recalculated_scores


def _content() -> dict:
    return {
        "comparison": {
            "rows": [
                {
                    "school": "가톨릭관동대학교",
                    "department": "스포츠재활의학전공",
                    "track": "실기 · 강원",
                    "converted": "498.214",
                    "max_total": "898.21",
                    "first_cut": "909.33",
                    "final_cut": "881.88",
                }
            ]
        }
    }


def _recommendation(*_args, **_kwargs) -> dict:
    return {
        "candidates": [
            {
                "university_id": "3",
                "university": "가톨릭관동대학교",
                "department": "스포츠재활의학전공",
                "admission_track": "실기",
                "student_record_score": 498.2143,
                "max_possible_total": 898.21,
                "prev_first_total": 909.33,
                "prev_final_total": 881.88,
            }
        ]
    }


def test_recalculated_scores_accept_display_rounding(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_recalc.recommend_candidates",
        _recommendation,
    )

    ok, errors, checks = validate_recalculated_scores("박시현", _content())

    assert ok is True, errors
    assert checks["recalculated_rows"] == 1


def test_recalculated_scores_reject_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_recalc.recommend_candidates",
        _recommendation,
    )
    content = _content()
    content["comparison"]["rows"][0]["converted"] = "123.45"

    ok, errors, _checks = validate_recalculated_scores("박시현", content)

    assert ok is False
    assert any("내신환산" in error for error in errors)


def test_recalculated_scores_reject_missing_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_recalc.recommend_candidates",
        lambda *_args, **_kwargs: {"candidates": []},
    )

    ok, errors, _checks = validate_recalculated_scores("박시현", _content())

    assert ok is False
    assert any("재산출 후보" in error for error in errors)


def test_recalculated_scores_refetch_row_when_not_in_top_candidates(monkeypatch) -> None:
    calls = []

    def fake_recommendation(*_args, **kwargs):
        calls.append(kwargs)
        if kwargs.get("university") == "가톨릭관동대학교":
            return _recommendation()
        return {"candidates": []}

    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_recalc.recommend_candidates",
        fake_recommendation,
    )

    ok, errors, checks = validate_recalculated_scores("박시현", _content())

    assert ok is True, errors
    assert checks["recalculated_rows"] == 1
    assert len(calls) == 2
