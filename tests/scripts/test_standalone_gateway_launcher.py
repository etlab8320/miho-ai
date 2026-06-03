from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_standalone_gateway(script_path: Path):
    loader = SourceFileLoader("_standalone_miho_gateway_under_test", str(script_path))
    spec = importlib.util.spec_from_loader(
        "_standalone_miho_gateway_under_test",
        loader,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standalone_gateway_prefers_dot_venv_python(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    py = repo / ".venv" / "bin" / "python"
    scripts.mkdir(parents=True)
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")

    source_script = Path(__file__).resolve().parents[2] / "scripts" / "miho-gateway"
    test_script = scripts / "miho-gateway"
    test_script.write_text(source_script.read_text(encoding="utf-8"), encoding="utf-8")

    module = _load_standalone_gateway(test_script)

    assert module.get_python_path() == str(py)
