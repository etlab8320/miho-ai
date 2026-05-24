from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_skill(relative: str) -> str:
    return (REPO_ROOT / relative / "SKILL.md").read_text(encoding="utf-8")


def test_miho_discord_workspace_skills_are_bundled():
    for skill in [
        "skills/devops/miho-discord-workspaces",
        "skills/devops/miho-discord-kanban-workspaces",
    ]:
        text = _read_skill(skill)
        assert text.startswith("---\n")
        assert "name: miho-discord" in text
        assert "RAG" in text or "Kanban" in text


def test_korean_law_and_tax_skills_require_current_official_sources():
    law = _read_skill("skills/korea/korean-law-research")
    tax = _read_skill("skills/korea/korean-tax-research")

    assert "law.go.kr" in law
    assert "glaw.scourt.go.kr" in law
    assert "current" in law.lower()
    assert "nts.go.kr" in tax
    assert "txsi.hometax.go.kr" in tax
    assert "Verify current rules" in tax


def test_kbo_skill_has_preview_review_prediction_guardrails():
    text = _read_skill("skills/sports/kbo-game-analysis")

    assert "kbo.co.kr" in text
    assert "Preview checklist" in text
    assert "Review checklist" in text
    assert "not betting advice" in text
