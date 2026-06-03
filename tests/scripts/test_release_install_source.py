"""Release installer source checks for Miho AI."""

from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "install.ps1",
    REPO_ROOT / "scripts" / "install.sh",
    REPO_ROOT / "scripts" / "install.ps1",
    REPO_ROOT / "scripts" / "install.cmd",
]


def test_release_installers_use_miho_ai_github_source():
    for path in RELEASE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "etlab8320/miho-ai" in text
        assert "NousResearch/miho-agent" not in text


def test_installers_show_miho_ai_branding():
    installer_files = [
        REPO_ROOT / "install.ps1",
        REPO_ROOT / "scripts" / "install.sh",
        REPO_ROOT / "scripts" / "install.ps1",
    ]
    for path in installer_files:
        text = path.read_text(encoding="utf-8")
        assert "Miho AI" in text
        assert "An open source AI agent by Nous Research." not in text


def test_update_source_defaults_to_main_release_branch():
    from miho_cli.update_source import DEFAULT_UPDATE_BRANCH, install_script_url

    assert DEFAULT_UPDATE_BRANCH == "main"
    assert install_script_url() == (
        "https://raw.githubusercontent.com/etlab8320/miho-ai/main/scripts/install.sh"
    )


def test_windows_root_installer_is_public_short_url_entrypoint():
    text = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "https://raw.githubusercontent.com/etlab8320/miho-ai/$ref/scripts/install.ps1" in text
    assert "raw.githubusercontent.com/etlab8320/miho-ai/main/install.ps1" in text


def test_release_profile_includes_local_embeddings_and_prefetch():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional = pyproject["project"]["optional-dependencies"]

    assert "fastembed==0.8.0" in optional["local-embeddings"]
    assert "miho-agent[local-embeddings]" in optional["all"]

    for path in (REPO_ROOT / "scripts" / "install.sh", REPO_ROOT / "scripts" / "install.ps1"):
        text = path.read_text(encoding="utf-8")
        assert "MIHO_SKIP_MODEL_PREFETCH" in text
        assert "intfloat/multilingual-e5-large" in text


def test_bash_installer_repairs_platform_sdks_before_gateway_start():
    text = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "install_platform_sdks()" in text
    assert "python-telegram-bot[webhooks]==22.6" in text
    assert "discord.py[voice]==2.7.1" in text
    assert "slack-sdk==3.40.1" in text

    main_body = text[text.index("main() {") :]
    assert main_body.index("run_setup_wizard") < main_body.index("install_platform_sdks")
    assert main_body.index("install_platform_sdks") < main_body.index("maybe_start_gateway")


def test_windows_installer_platform_sdks_use_locked_specs():
    text = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

    assert "python-telegram-bot[webhooks]==22.6" in text
    assert "discord.py[voice]==2.7.1" in text
    assert "slack-sdk==3.40.1" in text
    assert "slack-bolt==1.27.0" in text
    assert "qrcode==7.4.2" in text
