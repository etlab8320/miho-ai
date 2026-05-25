from scripts import release


def test_generate_changelog_uses_miho_ai_repository_links():
    commits = [
        {
            "sha": "abcdef1234567890",
            "short_sha": "abcdef12",
            "subject": "fix(windows): harden gateway install health",
            "category": "fixes",
            "scope": "windows",
            "github_author": "et",
        }
    ]

    changelog = release.generate_changelog(commits, "v0.15.6", "0.15.6", prev_tag="v0.15.5")

    assert "github.com/etlab8320/miho-ai" in changelog
    assert "github.com/NousResearch/miho-agent" not in changelog
