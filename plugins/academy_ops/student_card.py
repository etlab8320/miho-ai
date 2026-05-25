"""Build safe student-card data from PACA and Peak responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol


class AcademyClient(Protocol):
    def search_paca_students(self, query: str) -> list[dict[str, Any]]: ...
    def get_paca_student_detail(self, paca_student_id: int) -> dict[str, Any]: ...
    def list_peak_students(self) -> list[dict[str, Any]]: ...
    def get_peak_attendance(self, day: date) -> dict[str, Any]: ...
    def list_peak_records(self, peak_student_id: int) -> list[dict[str, Any]]: ...


class StudentCardError(RuntimeError):
    pass


class StudentCardNotFoundError(StudentCardError):
    pass


class StudentCardAmbiguousError(StudentCardError):
    pass


@dataclass(frozen=True)
class StudentProfile:
    paca_student_id: int
    peak_student_id: int | None
    name: str
    school: str
    grade: str
    gender: str
    status: str
    weekly_count: int | None
    time_slot: str


@dataclass(frozen=True)
class AttendanceSummary:
    today_status: str
    summary: dict[str, int]
    recent_absences: list[str]


@dataclass(frozen=True)
class RecordItem:
    event_name: str
    latest: float
    best: float
    unit: str
    delta: float | None
    trend: str
    measured_at: str
    average: float | None = None
    samples: tuple[float, ...] = ()


@dataclass(frozen=True)
class RiskSummary:
    level: str
    reasons: list[str]
    recommended_actions: list[str]
    judgment: str


@dataclass(frozen=True)
class StudentCard:
    profile: StudentProfile
    attendance: AttendanceSummary
    records: list[RecordItem]
    risk: RiskSummary
    missing_sources: list[str]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.__dict__.copy(),
            "attendance": {
                "today_status": self.attendance.today_status,
                "summary": self.attendance.summary.copy(),
                "recent_absences": list(self.attendance.recent_absences),
            },
            "records": {"items": [item.__dict__.copy() for item in self.records]},
            "risk": {
                "level": self.risk.level,
                "reasons": list(self.risk.reasons),
                "recommended_actions": list(self.risk.recommended_actions),
                "judgment": self.risk.judgment,
            },
            "missing_sources": list(self.missing_sources),
        }


class AcademyStudentCardService:
    def __init__(self, client: AcademyClient) -> None:
        self._client = client

    def build(
        self,
        student_query: str,
        *,
        today: date | None = None,
        period_days: int = 14,
    ) -> StudentCard:
        query = student_query.strip()
        if not query:
            raise StudentCardNotFoundError("학생 이름이나 검색어를 알려줘.")
        target_day = today or date.today()
        period = max(1, min(int(period_days or 14), 60))
        paca_student = self._select_student(query, self._client.search_paca_students(query))
        paca_id = _to_int(paca_student.get("id"))
        detail = self._client.get_paca_student_detail(paca_id)
        detail_student = detail.get("student") if isinstance(detail.get("student"), dict) else {}
        profile_source = {**paca_student, **detail_student}
        peak_student = self._find_peak_student(paca_id)
        peak_id = _to_int(peak_student.get("id")) if peak_student else None
        missing_sources: list[str] = []
        if peak_id is None:
            missing_sources.append("Peak 학생 매핑")

        attendance = self._attendance_summary(peak_id, target_day, period)
        if peak_id is None:
            records: list[RecordItem] = []
        else:
            records = self._record_items(self._client.list_peak_records(peak_id))
        if not records:
            missing_sources.append("Peak 기록")

        profile = StudentProfile(
            paca_student_id=paca_id,
            peak_student_id=peak_id,
            name=str(profile_source.get("name") or "이름 없음"),
            school=str(profile_source.get("school") or ""),
            grade=str(profile_source.get("grade") or ""),
            gender=str(profile_source.get("gender") or ""),
            status=str(profile_source.get("status") or ""),
            weekly_count=_optional_int(profile_source.get("weekly_count")),
            time_slot=str(profile_source.get("time_slot") or ""),
        )
        risk = self._risk_summary(profile, attendance, records, missing_sources)
        return StudentCard(profile, attendance, records, risk, missing_sources)

    def _select_student(self, query: str, students: list[dict[str, Any]]) -> dict[str, Any]:
        if not students:
            raise StudentCardNotFoundError("학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘.")
        exact = [item for item in students if str(item.get("name") or "").strip() == query]
        if len(exact) == 1:
            return exact[0]
        if len(students) == 1:
            return students[0]
        candidates = ", ".join(str(item.get("name") or "이름 없음") for item in students[:5])
        raise StudentCardAmbiguousError(f"동명이인이 있어. 학생을 조금 더 구체적으로 골라줘: {candidates}")

    def _find_peak_student(self, paca_student_id: int) -> dict[str, Any] | None:
        for student in self._client.list_peak_students():
            if _to_int(student.get("paca_student_id")) == paca_student_id:
                return student
        return None

    def _attendance_summary(
        self,
        peak_student_id: int | None,
        today: date,
        period_days: int,
    ) -> AttendanceSummary:
        counts = {"present": 0, "late": 0, "absent": 0}
        recent_absences: list[str] = []
        today_status = "unknown"
        if peak_student_id is None:
            return AttendanceSummary(today_status, counts, recent_absences)

        first_day = today - timedelta(days=period_days - 1)
        for offset in range(period_days):
            day = first_day + timedelta(days=offset)
            status = self._attendance_status_for_day(peak_student_id, day)
            if status in counts:
                counts[status] += 1
            if status == "absent":
                recent_absences.append(day.isoformat())
            if day == today and status:
                today_status = status
        return AttendanceSummary(today_status, counts, recent_absences[-5:])

    def _attendance_status_for_day(self, peak_student_id: int, day: date) -> str:
        payload = self._client.get_peak_attendance(day)
        slots = payload.get("slots") if isinstance(payload, dict) else {}
        if not isinstance(slots, dict):
            return ""
        for rows in slots.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and _to_int(row.get("student_id")) == peak_student_id:
                    return str(row.get("attendance_status") or row.get("status") or "")
        return ""

    def _record_items(self, rows: list[dict[str, Any]]) -> list[RecordItem]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = _record_group_key(row)
            if key:
                grouped.setdefault(key, []).append(row)
        items: list[RecordItem] = []
        for group in grouped.values():
            parsed = [row for row in group if _to_float(row.get("value")) is not None]
            parsed.sort(key=lambda row: str(row.get("measured_at") or ""), reverse=True)
            if not parsed:
                continue
            latest = parsed[0]
            values = [_to_float(row.get("value")) for row in parsed]
            numeric_values = [value for value in values if value is not None]
            direction = str(latest.get("direction") or "higher")
            latest_value = numeric_values[0]
            previous = numeric_values[1] if len(numeric_values) > 1 else None
            delta = _record_delta(latest_value, previous, direction)
            recent_samples = tuple(reversed(numeric_values[:6]))
            items.append(
                RecordItem(
                    event_name=str(latest.get("record_type_name") or "기록"),
                    latest=latest_value,
                    best=min(numeric_values) if direction == "lower" else max(numeric_values),
                    unit=str(latest.get("unit") or ""),
                    delta=delta,
                    trend=_trend(delta),
                    measured_at=str(latest.get("measured_at") or ""),
                    average=round(sum(numeric_values) / len(numeric_values), 2),
                    samples=recent_samples,
                )
            )
        items.sort(key=lambda item: item.measured_at, reverse=True)
        return items[:6]

    def _risk_summary(
        self,
        profile: StudentProfile,
        attendance: AttendanceSummary,
        records: list[RecordItem],
        missing_sources: list[str],
    ) -> RiskSummary:
        level = _risk_level(attendance, records)
        reasons = [_attendance_fact(attendance)]
        if any(item.trend == "down" for item in records):
            reasons.append("최근 기록 중 직전 측정보다 낮아진 종목이 있습니다.")
        if missing_sources:
            reasons.append("일부 자료가 아직 연결되지 않았습니다.")
        actions = _recommended_actions(level, attendance)
        judgment = _judgment_sentence(attendance, records)
        return RiskSummary(level, reasons, actions, judgment)


def _record_delta(latest: float, previous: float | None, direction: str) -> float | None:
    if previous is None:
        return None
    value = previous - latest if direction == "lower" else latest - previous
    return round(value, 2)


def _trend(delta: float | None) -> str:
    if delta is None or delta == 0:
        return "flat"
    return "up" if delta > 0 else "down"


def _risk_label(level: str) -> str:
    return {"stable": "안정", "caution": "주의", "danger": "위험"}.get(level, "확인")


def _risk_level(attendance: AttendanceSummary, records: list[RecordItem]) -> str:
    absent = attendance.summary["absent"]
    late = attendance.summary["late"]
    marked = sum(attendance.summary.values())
    present_like = attendance.summary["present"] + late
    rate = (present_like / marked) if marked else 1
    if attendance.today_status == "absent":
        return "caution"
    if absent >= 3:
        return "danger"
    if absent >= 2 or late >= 2 or (marked >= 6 and rate < 0.8):
        return "caution"
    if absent <= 1 and late <= 1 and rate >= 0.8:
        return "stable"
    return "caution" if any(item.trend == "down" for item in records) else "stable"


def _attendance_fact(attendance: AttendanceSummary) -> str:
    marked = sum(attendance.summary.values())
    if marked == 0:
        return "최근 출결 확인값이 아직 없습니다."
    return (
        f"최근 출결 확인값 {marked}건 중 출석 {attendance.summary['present']}회, "
        f"지각 {attendance.summary['late']}회, 결석 {attendance.summary['absent']}회입니다."
    )


def _recommended_actions(level: str, attendance: AttendanceSummary) -> list[str]:
    absent = attendance.summary["absent"]
    if attendance.today_status == "absent":
        return ["오늘 결석 사유와 다음 등원 가능일만 확인하면 됩니다."]
    if level == "danger":
        return ["경고 기준: 결석 3회 이상 또는 반복 결석입니다."]
    if level == "caution":
        return ["주의 기준: 결석 2회 이상, 지각 2회 이상, 또는 낮은 등원률입니다."]
    if absent == 1:
        return ["결석 1회는 위험 신호가 아니라 참고 항목으로만 표시합니다."]
    return ["별도 경고 기준에 걸린 출결 항목이 없습니다."]


def _judgment_sentence(attendance: AttendanceSummary, records: list[RecordItem]) -> str:
    parts = [_attendance_fact(attendance)]
    if records:
        parts.append(_records_fact(records))
    return " ".join(parts)


def _records_fact(records: list[RecordItem]) -> str:
    down_count = sum(1 for item in records if item.trend == "down")
    latest_names = ", ".join(item.event_name for item in records[:3])
    tail = f" 하락 표시 {down_count}종목." if down_count else ""
    return f"최근 기록 확인값 {len(records)}종목: {latest_names}.{tail}"


def _record_group_key(row: dict[str, Any]) -> str:
    record_type_id = str(row.get("record_type_id") or "").strip()
    record_type_name = str(row.get("record_type_name") or "").strip()
    if record_type_id and record_type_name:
        return f"{record_type_id}:{record_type_name}"
    return record_type_id or record_type_name


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
