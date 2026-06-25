"""Previous-year score scaling tests."""

from __future__ import annotations

import json
import sqlite3


def test_vs_prev_year_rescales_previous_practical_component(monkeypatch) -> None:
    from plugins.susi_ops import prev_year

    prev_year._PREV_PRACTICAL_MAX_CACHE.clear()
    monkeypatch.setattr(prev_year, "_vultr_mysql", lambda *_args, **_kwargs: [["1000"]])

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE susi_calculation_rules ("
        "university_id TEXT, admission_result_26_json TEXT, calculation_test_json TEXT, "
        "score_logic_json TEXT, admission_meta_json TEXT)"
    )
    conn.execute("CREATE TABLE db_university_rows (university_id TEXT, raw_json TEXT)")
    conn.execute(
        "INSERT INTO db_university_rows VALUES (?, ?)",
        ("221", json.dumps({"실기만점": "800"}, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO susi_calculation_rules VALUES (?, ?, ?, ?, ?)",
        (
            "221",
            json.dumps(
                {
                    "final_pass_cutoff": {
                        "total_score": 1136.290039,
                        "record_score": 186.289993,
                        "practical_score": 950.0,
                        "grade": 1,
                    }
                },
                ensure_ascii=False,
            ),
            json.dumps({"plugin_full_practical_total": 1000}, ensure_ascii=False),
            json.dumps({"grade_points": {"1": 188.5}}, ensure_ascii=False),
            json.dumps({"stage1": {"multiple": "4", "student_record": "", "other": "100"}}, ensure_ascii=False),
        ),
    )

    result = prev_year._vs_prev_year(conn, "221", 200.0)

    assert result is not None
    assert result["prev_final_total"] == 948.5
    assert result["max_possible_total"] == 1000.0
    assert result["reachable_at_full_practical"] is True
    assert result["stage1_uses_record"] is False
