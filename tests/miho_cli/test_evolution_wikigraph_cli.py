from __future__ import annotations

from miho_cli.evolution import cli_main
from miho_cli.commands import COMMAND_REGISTRY


def test_evolution_registry_includes_wikigraph():
    cmd = next(c for c in COMMAND_REGISTRY if c.name == "evolution")
    assert "wikigraph" in cmd.subcommands
    assert "wg" in cmd.subcommands
    assert "external-prompts" in cmd.subcommands
    assert "frontend-tools" in cmd.subcommands
    assert "install-hooks" in cmd.subcommands
    assert "visualize" in cmd.subcommands


def test_evolution_wikigraph_status_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho-home"))

    code = cli_main(["wikigraph", "status"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Miho System WikiGraph: ENABLED" in out
    assert "system_wiki" in out
    assert "system_graph" in out


def test_evolution_wikigraph_visualize_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho-home"))
    output = tmp_path / "map.html"

    code = cli_main(["wikigraph", "visualize", "gateway", "--output", str(output)])

    assert code == 0
    assert output.exists()
    assert "wikigraph: visualized" in capsys.readouterr().out


def test_evolution_wikigraph_relationships_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho-home"))
    output = tmp_path / "governance-relationships.html"

    code = cli_main(["wikigraph", "relationships", "--output", str(output)])

    assert code == 0
    assert output.exists()
    out = capsys.readouterr().out
    assert "wikigraph: relationships visualized" in out
    assert "edges=" in out


def test_evolution_wikigraph_external_prompts_sync_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho-home"))
    source = tmp_path / "external-prompts"
    source.mkdir()
    (source / "agent.md").write_text("Use tools, protect secrets, run tests.", encoding="utf-8")

    rc = cli_main(["wikigraph", "external-prompts", "sync", "--source", str(source)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "wikigraph: external prompt corpus synced" in out
    assert "artifacts_indexed=1" in out


def test_evolution_wikigraph_frontend_tools_sync_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho-home"))

    rc = cli_main(["wikigraph", "frontend-tools", "sync"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "wikigraph: frontend tool corpus synced" in out
    assert "tools_indexed=" in out
