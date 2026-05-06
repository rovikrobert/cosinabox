from pathlib import Path

USER_REPO_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "src" / "cosinabox" / "templates" / "user-repo"
)


def test_user_repo_claude_md_under_200_lines() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    assert len(text.splitlines()) < 200


def test_user_repo_claude_md_lists_subdocs() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    for sub in (
        "safety.md",
        "persona-interview.md",
        "editing-config.md",
        "adding-custom-jobs.md",
        "oauth-walkthrough.md",
        "proactive-suggestions.md",
    ):
        assert sub in text


def test_user_repo_dockerfile_forces_eager_pip_upgrade() -> None:
    """Regression: pin must be resolved against PyPI on every build.

    Without --upgrade-strategy eager, pip's default (only-if-needed) will
    skip cosinabox upgrades when the baked base-image version satisfies
    the pin — and Railway's docker layer cache keeps the same base-image
    digest across redeploys, so a deploy can stay frozen on an old patch
    indefinitely. Bit us live: rovik-keevs ran 0.1.2 even after 0.1.4 was
    published with the floating :0.1 tag retagged.
    """
    text = (USER_REPO_TEMPLATE / "Dockerfile").read_text()
    assert "--upgrade-strategy eager" in text, (
        "Dockerfile must use `--upgrade-strategy eager` so deploys pick up "
        "cosinabox patch releases. See the inline comment in the template."
    )
