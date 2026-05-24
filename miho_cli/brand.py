"""Runtime brand selection for Miho-based distributions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from miho_cli.miho_persona import MIHO_SYSTEM_PROMPT


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


MIHO_BRAND = RuntimeBrand(
    key="miho",
    product_name="Miho AI",
    short_name="Miho",
    command_name="miho",
    default_skin="miho",
    home_env_var="MIHO_HOME",
    default_home_dir=".miho",
    system_prompt=MIHO_SYSTEM_PROMPT,
    discord_status="Miho AI",
)


def current_brand() -> RuntimeBrand:
    miho_runtime = os.getenv("MIHO_RUNTIME", "").strip().lower()
    miho_brand = os.getenv("MIHO_BRAND", "").strip().lower()
    skin = os.getenv("MIHO_DEFAULT_SKIN", "").strip().lower()
    if miho_runtime in {"1", "true", "yes", "on"} or miho_brand in {"miho", "miho-ai", "miho_ai"}:
        return MIHO_BRAND
    if skin == "miho":
        return MIHO_BRAND
    return MIHO_BRAND


def current_brand_name() -> str:
    return current_brand().product_name


def current_gateway_name() -> str:
    return f"{current_brand().short_name} Gateway"


def default_brand_home(brand: RuntimeBrand | None = None) -> Path:
    runtime_brand = brand or current_brand()
    return Path.home() / runtime_brand.default_home_dir
