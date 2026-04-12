def test_package_imports() -> None:
    import cosinabox

    assert cosinabox.__version__ == "0.1.0"


def test_cli_imports() -> None:
    from cosinabox.cli.main import cli

    assert cli.name == "cli"
