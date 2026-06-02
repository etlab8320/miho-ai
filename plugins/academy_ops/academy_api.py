"""Authenticated PACA/Peak API client for academy operations."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from .paca_config import AcademyConfigError, resolve_paca_base_url


class AcademyApiError(RuntimeError):
    """Raised when PACA/Peak data cannot be fetched safely."""


class AcademyApiClient:
    def __init__(
        self,
        *,
        token: str,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        try:
            self._base_url = resolve_paca_base_url(base_url)
        except AcademyConfigError as exc:
            raise AcademyApiError(str(exc)) from exc
        self._transport = transport
        self._timeout = timeout

    def search_paca_students(self, query: str) -> list[dict[str, Any]]:
        payload = self._get("/paca/students", params={"search": query.strip()})
        return _student_rows(payload)

    def list_paca_students(self, *, status: str = "") -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        payload = self._get("/paca/students", params=params)
        return _student_rows(payload)

    def get_paca_student_detail(self, paca_student_id: int) -> dict[str, Any]:
        payload = self._get(f"/paca/students/{paca_student_id}")
        return payload if isinstance(payload, dict) else {}

    def list_paca_instructors(self, *, status: str = "active") -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        payload = self._get("/paca/instructors", params=params)
        instructors = payload.get("instructors") if isinstance(payload, dict) else None
        return [item for item in instructors or [] if isinstance(item, dict)]

    def get_paca_instructor_attendance(
        self,
        instructor_id: int,
        *,
        year: int,
        month: int,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"/paca/instructors/{instructor_id}/attendance",
            params={"year": str(year), "month": str(month)},
        )
        attendances = payload.get("attendances") if isinstance(payload, dict) else None
        return [item for item in attendances or [] if isinstance(item, dict)]

    def get_paca_academy_events(self, start_day: date, end_day: date) -> list[dict[str, Any]]:
        payload = self._get(
            "/paca/academy-events",
            params={"start_date": start_day.isoformat(), "end_date": end_day.isoformat()},
        )
        events = payload.get("events") if isinstance(payload, dict) else None
        return [item for item in events or [] if isinstance(item, dict)]

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict[str, Any]]:
        payload = self._get(
            "/paca/schedules",
            params={"start_date": start_day.isoformat(), "end_date": end_day.isoformat()},
        )
        schedules = payload.get("schedules") if isinstance(payload, dict) else None
        return [item for item in schedules or [] if isinstance(item, dict)]

    def get_paca_schedule_attendance(self, schedule_id: int) -> dict[str, Any]:
        payload = self._get(f"/paca/schedules/{schedule_id}/attendance")
        return payload if isinstance(payload, dict) else {}

    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict[str, Any]:
        payload = self._get(f"/paca/students/{paca_student_id}/attendance", params={"year_month": year_month})
        return payload if isinstance(payload, dict) else {}

    def list_paca_consultations(self, *, limit: int = 100, max_pages: int = 10) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            payload = self._get("/paca/consultations", params={"page": str(page), "limit": str(limit)})
            consultations = payload.get("consultations") if isinstance(payload, dict) else None
            rows.extend(item for item in consultations or [] if isinstance(item, dict))
            pagination = payload.get("pagination") if isinstance(payload, dict) else {}
            if not isinstance(pagination, dict) or page >= _to_int(pagination.get("totalPages")):
                break
        return rows

    def get_consultation_candidates(self, *, today: date, attendance_days: int = 14, limit: int = 10) -> dict[str, Any]:
        payload = self._get(
            "/paca/consultation-candidates",
            params={
                "today": today.isoformat(),
                "attendance_days": str(attendance_days),
                "limit": str(limit),
            },
        )
        return payload if isinstance(payload, dict) else {}

    def list_peak_monthly_tests(self) -> list[dict[str, Any]]:
        payload = self._get("/peak/monthly-tests")
        tests = payload.get("tests") if isinstance(payload, dict) else None
        return [item for item in tests or [] if isinstance(item, dict)]

    def get_peak_monthly_test_records(self, monthly_test_id: int) -> dict[str, Any]:
        payload = self._get(f"/peak/monthly-tests/{monthly_test_id}/all-records")
        return payload if isinstance(payload, dict) else {}

    def get_student_context(self, query: str, *, today: date, period_days: int = 14) -> dict[str, Any]:
        payload = self._get(
            "/paca/student-context",
            params={
                "q": query.strip(),
                "today": today.isoformat(),
                "period_days": str(period_days),
            },
        )
        return payload if isinstance(payload, dict) else {}

    def list_peak_students(self) -> list[dict[str, Any]]:
        payload = self._get("/peak/students")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        students = payload.get("students") if isinstance(payload, dict) else None
        return [item for item in students or [] if isinstance(item, dict)]

    def get_peak_attendance(self, day: date) -> dict[str, Any]:
        payload = self._get("/peak/attendance/students", params={"date": day.isoformat()})
        return payload if isinstance(payload, dict) else {}

    def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict[str, Any]:
        params = {"date": day.isoformat()}
        if time_slot:
            params["time_slot"] = time_slot
        payload = self._get("/peak/assignments", params=params)
        return payload if isinstance(payload, dict) else {}

    def get_peak_plans(self, day: date, *, time_slot: str = "") -> dict[str, Any]:
        params = {"date": day.isoformat()}
        if time_slot:
            params["time_slot"] = time_slot
        payload = self._get("/peak/plans", params=params)
        return payload if isinstance(payload, dict) else {}

    def list_peak_records(self, peak_student_id: int) -> list[dict[str, Any]]:
        payload = self._get("/peak/records", params={"student_id": str(peak_student_id)})
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        records = payload.get("records") if isinstance(payload, dict) else None
        return [item for item in records or [] if isinstance(item, dict)]

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                response = client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise AcademyApiError("학원 서버에 연결하지 못했어. 잠시 후 다시 시도해줘.") from exc

        if response.status_code in {401, 403}:
            raise AcademyApiError("학원 계정 연결이 만료된 것 같아. `/academy login`으로 다시 연결해줘.")
        if response.status_code == 404:
            raise AcademyApiError("학원 서버에서 필요한 조회 경로를 찾지 못했어.")
        if response.status_code == 409:
            raise AcademyApiError(_conflict_message(response))
        if response.status_code >= 500:
            raise AcademyApiError("학원 서버가 잠시 불안정해. 잠시 후 다시 시도해줘.")
        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AcademyApiError("학원 서버 응답을 확인하지 못했어. 잠시 후 다시 시도해줘.") from exc


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _student_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    students = payload.get("students") if isinstance(payload, dict) else None
    return [item for item in students or [] if isinstance(item, dict)]


def _conflict_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "학생이 여러 명 검색됐어. 이름이나 학교를 조금 더 정확히 알려줘."
    message = str(payload.get("message") or "학생이 여러 명 검색됐어. 이름이나 학교를 조금 더 정확히 알려줘.")
    candidates = payload.get("candidates") if isinstance(payload, dict) else []
    names = []
    for item in candidates if isinstance(candidates, list) else []:
        if isinstance(item, dict):
            label = " ".join(str(item.get(key) or "").strip() for key in ("name", "school", "grade") if item.get(key))
            if label:
                names.append(label)
    return f"{message} 후보: {', '.join(names[:5])}" if names else message
