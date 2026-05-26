"""Tests for Korean academy date parsing."""

from __future__ import annotations

from datetime import date

from plugins.academy_ops.date_parser import parse_academy_date


def test_parse_academy_date_reads_korean_month_day_without_year() -> None:
    assert parse_academy_date("5월24일에 출근한 강사", today=date(2026, 5, 26)) == date(2026, 5, 24)
    assert parse_academy_date("5월 24일 출근 강사", today=date(2026, 5, 26)) == date(2026, 5, 24)


def test_parse_academy_date_reads_korean_year_month_day() -> None:
    assert parse_academy_date("2025년 12월 31일 출근 강사", today=date(2026, 5, 26)) == date(2025, 12, 31)


def test_parse_academy_date_reads_numeric_month_day_forms() -> None:
    assert parse_academy_date("5/24 출근 강사", today=date(2026, 5, 26)) == date(2026, 5, 24)
    assert parse_academy_date("05.24 출근 강사", today=date(2026, 5, 26)) == date(2026, 5, 24)
