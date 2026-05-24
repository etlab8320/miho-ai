"""Runtime brand selection for Hermes-based distributions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class RuntimeBrand:
    key: str
    product_name: str
    short_name: str
    command_name: str
    default_skin: str
    home_env_var: str
    default_home_dir: str
    system_prompt: str
    discord_status: str


HERMES_BRAND = RuntimeBrand(
    key="hermes",
    product_name="Hermes Agent",
    short_name="Hermes",
    command_name="hermes",
    default_skin="default",
    home_env_var="HERMES_HOME",
    default_home_dir=".hermes",
    system_prompt="",
    discord_status="agent work",
)

MIHO_BRAND = RuntimeBrand(
    key="miho",
    product_name="Miho AI",
    short_name="Miho",
    command_name="miho",
    default_skin="miho",
    home_env_var="MIHO_HOME",
    default_home_dir=".miho",
    system_prompt=(
        "You are Miho AI, a Discord-first work agent based on Hermes Agent. "
        "Be fast, accurate, and practical. Read context carefully, verify "
        "before claiming, and keep user-facing replies clear and polished. "
        "For Korean users, answer in natural Korean unless asked otherwise. "
        "When giving user-facing CLI instructions, use the `miho` command "
        "and the `~/.miho` home directory. Do not tell users to run `hermes` "
        "or edit `~/.hermes` unless they explicitly ask about upstream Hermes "
        "internals. Do not over-explain tool use; deliver useful results."
    ),
    discord_status="Miho AI",
)


def current_brand() -> RuntimeBrand:
    raw = os.getenv("HERMES_BRAND", "").strip().lower()
    skin = os.getenv("HERMES_DEFAULT_SKIN", "").strip().lower()
    if raw in {"miho", "miho-ai", "miho_ai"} or skin == "miho":
        return MIHO_BRAND
    return HERMES_BRAND


def current_brand_name() -> str:
    return current_brand().product_name


def default_brand_home(brand: RuntimeBrand | None = None) -> Path:
    runtime_brand = brand or current_brand()
    return Path.home() / runtime_brand.default_home_dir
