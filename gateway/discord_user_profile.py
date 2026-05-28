"""Per-Discord-user profile storage and prompt context."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from miho_constants import get_miho_home
from utils import atomic_json_write


_SAFE_ID_RE = re.compile(r"[^0-9A-Za-z_.-]+")
_LIST_LIMIT = 6
_TEXT_LIMIT = 240


def profile_path_for_discord_user(user_id: str) -> Path:
    safe_id = _safe_user_id(user_id)
    return get_miho_home() / "discord" / "users" / safe_id / "profile.json"


def load_discord_user_profile(user_id: str) -> dict[str, Any]:
    path = profile_path_for_discord_user(user_id)
    try:
        data = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_profile(user_id)
    except OSError:
        return _empty_profile(user_id)
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return _empty_profile(user_id)
    if not isinstance(payload, dict):
        return _empty_profile(user_id)
    base = _empty_profile(user_id)
    base.update({key: value for key, value in payload.items() if key in base or key == "notes"})
    base["discord_user_id"] = str(user_id)
    return base


def upsert_discord_user_profile(
    user_id: str,
    *,
    preferred_name: str = "",
    main_use_cases: list[str] | None = None,
    response_style: str = "",
    important_boundaries: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    profile = load_discord_user_profile(user_id)
    if preferred_name:
        profile["preferred_name"] = _compact_text(preferred_name)
    if main_use_cases is not None:
        profile["main_use_cases"] = _compact_list(main_use_cases)
    if response_style:
        profile["response_style"] = _compact_text(response_style)
    if important_boundaries is not None:
        profile["important_boundaries"] = _compact_list(important_boundaries)
    if notes:
        profile["notes"] = _compact_text(notes)
    profile["updated_at"] = _now_iso()
    _write_profile(profile)
    return profile


def mark_onboarding_prompted(user_id: str) -> dict[str, Any]:
    profile = load_discord_user_profile(user_id)
    if not profile.get("onboarding_prompted_at"):
        profile["onboarding_prompted_at"] = _now_iso()
        profile["updated_at"] = profile["onboarding_prompted_at"]
        _write_profile(profile)
    return profile


def should_prompt_onboarding(profile: dict[str, Any]) -> bool:
    return not profile_has_user_fields(profile) and not profile.get("onboarding_prompted_at")


def profile_has_user_fields(profile: dict[str, Any]) -> bool:
    if str(profile.get("preferred_name") or "").strip():
        return True
    if str(profile.get("response_style") or "").strip():
        return True
    if str(profile.get("notes") or "").strip():
        return True
    for key in ("main_use_cases", "important_boundaries"):
        values = profile.get(key)
        if isinstance(values, list) and any(str(item or "").strip() for item in values):
            return True
    return False


def build_discord_user_profile_context(user_id: str, user_name: str = "") -> str:
    if not user_id:
        return ""
    profile = load_discord_user_profile(user_id)
    if should_prompt_onboarding(profile):
        mark_onboarding_prompted(user_id)
        return _onboarding_context(user_name)
    if not profile_has_user_fields(profile):
        return ""
    return _profile_context(profile)


def _profile_context(profile: dict[str, Any]) -> str:
    lines = [
        "### Relevant Discord User Profile",
        "Use this only for the current Discord user; do not mix it with other users.",
    ]
    preferred_name = str(profile.get("preferred_name") or "").strip()
    if preferred_name:
        lines.append(f"- preferred_name: {preferred_name}")
    use_cases = _string_list(profile.get("main_use_cases"))
    if use_cases:
        lines.append(f"- main_use_cases: {', '.join(use_cases)}")
    response_style = str(profile.get("response_style") or "").strip()
    if response_style:
        lines.append(f"- response_style: {response_style}")
    boundaries = _string_list(profile.get("important_boundaries"))
    if boundaries:
        lines.append(f"- important_boundaries: {', '.join(boundaries)}")
    notes = str(profile.get("notes") or "").strip()
    if notes:
        lines.append(f"- notes: {notes}")
    return "\n".join(lines)


def _onboarding_context(user_name: str = "") -> str:
    label = _compact_text(user_name) or "this Discord user"
    return "\n".join(
        [
            "### Discord User Profile Onboarding",
            f"- No saved profile exists for {label}.",
            "- After answering the user's current request, briefly ask up to three optional onboarding questions in Korean.",
            "- Ask for preferred_name, main_use_cases, and response_style.",
            "- If the user answers, save only what they explicitly provided with the discord_profile tool.",
            "- Do not save this Discord user's profile into owner_profile or shared USER.md.",
            "- Make onboarding skippable and do not mention internal storage paths.",
        ]
    )


def _write_profile(profile: dict[str, Any]) -> None:
    path = profile_path_for_discord_user(str(profile.get("discord_user_id") or "unknown"))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(path, profile, indent=2)


def _empty_profile(user_id: str) -> dict[str, Any]:
    return {
        "discord_user_id": str(user_id),
        "preferred_name": "",
        "main_use_cases": [],
        "response_style": "",
        "important_boundaries": [],
        "notes": "",
        "onboarding_prompted_at": "",
        "updated_at": "",
    }


def _safe_user_id(user_id: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", str(user_id or "").strip())
    return cleaned or "unknown"


def _compact_text(value: str) -> str:
    return " ".join(str(value or "").split())[:_TEXT_LIMIT]


def _compact_list(values: list[str] | None) -> list[str]:
    return [_compact_text(str(item)) for item in (values or []) if _compact_text(str(item))][:_LIST_LIMIT]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
