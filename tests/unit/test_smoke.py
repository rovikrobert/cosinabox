def test_package_imports() -> None:
    import re

    import cosinabox

    # Version-agnostic — asserts shape rather than a specific string so
    # the next bump doesn't break CI (0.1.0 → 0.1.1 already did that once).
    assert re.match(r"^\d+\.\d+\.\d+", cosinabox.__version__)


def test_cli_imports() -> None:
    from cosinabox.cli.main import cli

    assert cli.name == "cli"
