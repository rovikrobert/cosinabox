from pathlib import Path

USER_REPO_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src" / "cosinabox" / "templates" / "user-repo"
)


def test_user_repo_claude_md_under_200_lines() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    assert len(text.splitlines()) < 200


def test_user_repo_claude_md_lists_subdocs() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    for sub in ("safety.md", "persona-interview.md", "editing-config.md",
                "adding-custom-jobs.md", "oauth-walkthrough.md",
                "proactive-suggestions.md"):
        assert sub in text
