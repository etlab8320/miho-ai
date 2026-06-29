from __future__ import annotations

from miho_cli.evolution import cli_main
from miho_cli.commands import COMMAND_REGISTRY


def test_evolution_registry_includes_wikigraph():
    cmd = next(c for c in COMMAND_REGISTRY if c.name == "evolution")
    assert "wikigraph" in cmd.subcommands
    assert "wg" in cmd.subcommands
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
