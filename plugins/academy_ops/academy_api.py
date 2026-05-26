"""Authenticated PACA/Peak API client for academy operations."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from .paca_client import DEFAULT_PACA_BASE_URL


class AcademyApiError(RuntimeError):
    """Raised when PACA/Peak data cannot be fetched safely."""


class AcademyApiClient:
    def __init__(
        self,
        *,
        token: str,
        base_url: str = DEFAULT_PACA_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def search_paca_students(self, query: str) -> list[dict[str, Any]]:
        payload = self._get("/paca/students", params={"search": query.strip()})
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        students = payload.get("students") if isinstance(payload, dict) else None
        return [item for item in students or [] if isinstance(item, dict)]

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

    def list_peak_students(self) -> list[dict[str, Any]]:
        payload = self._get("/peak/students")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        students = payload.get("students") if isinstance(payload, dict) else None
        return [item for item in students or [] if isinstance(item, dict)]

    def get_peak_attendance(self, day: date) -> dict[str, Any]:
        payload = self._get("/peak/attendance/students", params={"date": day.isoformat()})
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
        if response.status_code >= 500:
            raise AcademyApiError("학원 서버가 잠시 불안정해. 잠시 후 다시 시도해줘.")
        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AcademyApiError("학원 서버 응답을 확인하지 못했어. 잠시 후 다시 시도해줘.") from exc
