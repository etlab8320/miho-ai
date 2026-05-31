"""Tests for _prefetch_local_embedding_model — the update-time mirror of
scripts/install.sh's prefetch_embedding_model.

These cover only the safe skip/no-op branches. The actual ~2GB model download
is never triggered: the fastembed-present branch is asserted via the subprocess
command it would run, not by executing it.
"""

import subprocess
from unittest.mock import patch

from miho_cli.main import _prefetch_local_embedding_model


class TestPrefetchLocalEmbeddingModel:
    def test_skips_when_env_flag_set(self, monkeypatch):
        monkeypatch.setenv("MIHO_SKIP_MODEL_PREFETCH", "1")
        with patch("subprocess.run") as mock_run:
            _prefetch_local_embedding_model()
        # Honoring the skip flag must not invoke any subprocess.
        mock_run.assert_not_called()

    def test_skips_when_fastembed_missing(self, monkeypatch):
        monkeypatch.delenv("MIHO_SKIP_MODEL_PREFETCH", raising=False)

        def side_effect(cmd, **kwargs):
            joined = " ".join(str(c) for c in cmd)
            # The `import fastembed` probe fails -> keyword fallback path.
            if "import fastembed" in joined:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            raise AssertionError(f"unexpected subprocess after failed probe: {joined}")

        with patch("subprocess.run", side_effect=side_effect) as mock_run:
            _prefetch_local_embedding_model()

        # Only the probe runs; the model-download snippet is never invoked.
        assert mock_run.call_count == 1

    def test_runs_prefetch_when_fastembed_present(self, monkeypatch):
        monkeypatch.delenv("MIHO_SKIP_MODEL_PREFETCH", raising=False)
        monkeypatch.delenv("MIHO_LOCAL_EMBEDDING_MODEL", raising=False)

        commands = []

        def side_effect(cmd, **kwargs):
            commands.append(" ".join(str(c) for c in cmd))
            # Probe succeeds, snippet "succeeds" — no real download happens
            # because subprocess.run is mocked.
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=side_effect):
            _prefetch_local_embedding_model()

        # Probe ran, then the TextEmbedding download snippet ran.
        assert any("import fastembed" in c for c in commands)
        assert any("TextEmbedding" in c for c in commands)
