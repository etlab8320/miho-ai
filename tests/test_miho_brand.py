"""Tests for the Miho AI runtime brand layer."""

from __future__ import annotations


def test_default_brand_is_hermes(monkeypatch):
    from hermes_cli.brand import current_brand

    monkeypatch.delenv("HERMES_BRAND", raising=False)
    monkeypatch.delenv("HERMES_DEFAULT_SKIN", raising=False)

    brand = current_brand()

    assert brand.key == "hermes"
    assert brand.product_name == "Hermes Agent"


def test_miho_brand_from_env(monkeypatch):
    from hermes_cli.brand import current_brand

    monkeypatch.setenv("HERMES_BRAND", "miho")

    brand = current_brand()

    assert brand.key == "miho"
    assert brand.product_name == "Miho AI"
    assert brand.default_skin == "miho"
    assert "Miho AI" in brand.system_prompt


def test_miho_brand_from_default_skin(monkeypatch):
    from hermes_cli.brand import current_brand

    monkeypatch.delenv("HERMES_BRAND", raising=False)
    monkeypatch.setenv("HERMES_DEFAULT_SKIN", "miho")

    assert current_brand().key == "miho"


def test_cli_config_uses_miho_default_prompt(monkeypatch):
    from cli import load_cli_config

    monkeypatch.setenv("HERMES_BRAND", "miho")
    monkeypatch.setenv("HERMES_DEFAULT_SKIN", "miho")

    cfg = load_cli_config()

    assert cfg["display"]["skin"] == "miho"
    assert "Miho AI" in cfg["agent"]["system_prompt"]


def test_gateway_prompt_uses_miho_default_when_config_empty(tmp_path, monkeypatch):
    from gateway.run import GatewayRunner
    import gateway.run as gateway_run

    monkeypatch.setenv("HERMES_BRAND", "miho")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)

    prompt = GatewayRunner._load_ephemeral_system_prompt()

    assert "Miho AI" in prompt
