"""Runtime configuration for PACA/Peak API access."""

from __future__ import annotations

import os


PACA_BASE_URL_ENV = "MIHO_ACADEMY_PACA_BASE_URL"
PACA_BASE_URL_CONFIG_KEY = ("academy_ops", "paca_base_url")
PACA_CONFIG_ERROR_MESSAGE = "학원 서버 연결 설정을 확인하지 못했어. 관리자에게 문의해줘."


class AcademyConfigError(RuntimeError):
    pass


def resolve_paca_base_url(base_url: str | None = None) -> str:
    explicit = str(base_url or "").strip()
    if explicit:
        return explicit.rstrip("/")

    env_value = os.getenv(PACA_BASE_URL_ENV, "").strip()
    if env_value:
        return env_value.rstrip("/")

    cfg_value = _configured_paca_base_url()
    if cfg_value:
        return cfg_value.rstrip("/")

    raise AcademyConfigError(PACA_CONFIG_ERROR_MESSAGE)


def _configured_paca_base_url() -> str:
    try:
        from miho_cli.config import cfg_get, load_config

        value = cfg_get(load_config(), *PACA_BASE_URL_CONFIG_KEY, default="")
    except Exception:
        return ""
    return value.strip() if isinstance(value, str) else ""
