"""Tests for the Miho AI runtime brand layer."""

from __future__ import annotations


def test_default_brand_is_miho(monkeypatch):
    from miho_cli.brand import current_brand

    monkeypatch.delenv("MIHO_BRAND", raising=False)
    monkeypatch.delenv("MIHO_DEFAULT_SKIN", raising=False)

    brand = current_brand()

    assert brand.key == "miho"
    assert brand.product_name == "Miho AI"


def test_miho_brand_from_env(monkeypatch):
    from miho_cli.brand import current_brand

    monkeypatch.setenv("MIHO_BRAND", "miho")

    brand = current_brand()

    assert brand.key == "miho"
    assert brand.product_name == "Miho AI"
    assert brand.default_skin == "miho"
    assert "Miho AI" in brand.system_prompt
    assert "`miho` command" in brand.system_prompt
    assert "`~/.miho`" in brand.system_prompt
    assert "Never expose fork or upstream internals" in brand.system_prompt
    assert "gumiho" in brand.system_prompt
    assert "For Korean users, answer in natural Korean" in brand.system_prompt
    assert "Charm is the surface; competence is the core." in brand.system_prompt


def test_miho_brand_from_default_skin(monkeypatch):
    from miho_cli.brand import current_brand

    monkeypatch.delenv("MIHO_BRAND", raising=False)
    monkeypatch.setenv("MIHO_DEFAULT_SKIN", "miho")

    assert current_brand().key == "miho"


def test_gateway_name_follows_runtime_brand(monkeypatch):
    from miho_cli.brand import current_gateway_name

    monkeypatch.delenv("MIHO_BRAND", raising=False)
    monkeypatch.delenv("MIHO_DEFAULT_SKIN", raising=False)

    assert current_gateway_name() == "Miho Gateway"

    monkeypatch.setenv("MIHO_BRAND", "miho")

    assert current_gateway_name() == "Miho Gateway"


def test_cli_config_uses_miho_default_prompt(monkeypatch):
    from cli import load_cli_config

    monkeypatch.setenv("MIHO_BRAND", "miho")
    monkeypatch.setenv("MIHO_DEFAULT_SKIN", "miho")

    cfg = load_cli_config()

    assert cfg["display"]["skin"] == "miho"
    assert "Miho AI" in cfg["agent"]["system_prompt"]


def test_gateway_prompt_uses_miho_default_when_config_empty(tmp_path, monkeypatch):
    from gateway.run import GatewayRunner
    import gateway.run as gateway_run

    monkeypatch.setenv("MIHO_BRAND", "miho")
    monkeypatch.setattr(gateway_run, "_miho_home", tmp_path)

    prompt = GatewayRunner._load_ephemeral_system_prompt()

    assert "Miho AI" in prompt
