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
    assert "kbo-report-cards" in text


def test_kbo_report_cards_require_html_player_photos_and_media_delivery():
    text = _read_skill("skills/sports/kbo-report-cards")
    quality = (REPO_ROOT / "skills/sports/kbo-report-cards/references/kbo-card-quality.md").read_text(
        encoding="utf-8"
    )
    template = REPO_ROOT / "skills/sports/kbo-report-cards/templates/kbo-card.html"

    assert "name: kbo-report-cards" in text
    assert "Build source HTML first" in text
    assert "MEDIA:/absolute/path" in text
    assert "Player Photos" in text
    assert "원정" in text
    assert "방문" in text
    assert "data URIs" in text
    assert "bottom clipping" in quality
    assert template.is_file()


def test_sports_report_card_is_visual_layer_for_html_first_media():
    text = _read_skill("skills/sports/sports-report-card")

    assert "HTML/CSS first" in text
    assert "MEDIA:<path>" in text
    assert "Goyang" in text
