from __future__ import annotations

import re
from pathlib import Path


SKILL_PATH = Path("skills/creative/product-ui-design/SKILL.md")


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter_value(name: str) -> str:
    match = re.search(rf"^{name}:\s*(.+)$", _skill_text(), re.MULTILINE)
    assert match, f"{name} missing from frontmatter"
    return match.group(1).strip().strip('"')


def test_product_ui_design_skill_exists_with_short_description() -> None:
    assert SKILL_PATH.is_file()
    assert _frontmatter_value("name") == "product-ui-design"
    assert len(_frontmatter_value("description")) <= 60


def test_product_ui_design_routes_to_existing_design_skills() -> None:
    text = _skill_text()

    for skill_name in ("claude-design", "sketch", "popular-web-designs", "design-md"):
        assert skill_name in text


def test_product_ui_design_has_production_quality_gates() -> None:
    text = _skill_text().lower()

    for phrase in (
        "existing project",
        "responsive",
        "console",
        "error states",
        "accessibility",
        "do not invent fake metrics",
    ):
        assert phrase in text


def test_product_ui_design_marks_templates_as_supporting_material() -> None:
    text = _skill_text().lower()

    assert "reference library" in text
    assert "not the source of truth" in text
