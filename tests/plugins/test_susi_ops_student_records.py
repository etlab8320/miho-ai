from __future__ import annotations

from plugins.susi_ops.student_records import _parse_career_ratio_table, parse_raw_score


def test_parse_raw_score_with_mean_and_standard_deviation() -> None:
    assert parse_raw_score("81/89.6(13.3)") == (81.0, 89.6, 13.3)
    assert parse_raw_score(None) == (None, None, None)


def test_parse_career_ratio_table_reads_semester_distribution_rows() -> None:
    text = """
<진로 선택 과목>
     국어        심화 국어         2        43/71.9        C(217)    A(45.6) B(31.3) C(23.0)
     수학        수학과제 탐구       3        49/64.1        C(167)    A(24.6) B(29.3) C(46.1)
 1
     영어        진로 영어         2        27/70.2         C(191)   A(37.7) B(33.5) C(28.8)
     국어        심화 국어         2        36/68.0        C(216)    A(37.0) B(24.1) C(38.9)
 2   영어        진로 영어           2        37/56.5        C(191)   A(14.1) B(24.1) C(61.8)
"""

    ratios = _parse_career_ratio_table(text)

    assert ratios[(3, 1, "심화 국어")] == {"A": 45.6, "B": 31.3, "C": 23.0}
    assert ratios[(3, 1, "수학과제 탐구")] == {"A": 24.6, "B": 29.3, "C": 46.1}
    assert ratios[(3, 1, "진로 영어")] == {"A": 37.7, "B": 33.5, "C": 28.8}
    assert ratios[(3, 2, "심화 국어")] == {"A": 37.0, "B": 24.1, "C": 38.9}
    assert ratios[(3, 2, "진로 영어")] == {"A": 14.1, "B": 24.1, "C": 61.8}
