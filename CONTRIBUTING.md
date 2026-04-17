# Contributing to CoSinaBox

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/user/cosinabox.git
cd cosinabox
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,google,fireflies,search,attio]"
pre-commit install
```

Requires Python 3.11+.

## Running Tests

```bash
pytest                  # full suite
pytest tests/unit/      # unit tests only
pytest tests/stress/    # stress tests
```

Tests must pass before opening a PR. CI runs `pytest`, `ruff check`, and `mypy --strict` on every push.

## Code Style

- **Linter:** [ruff](https://docs.astral.sh/ruff/) (line length 100, Python 3.11)
- **Type checking:** [mypy](https://mypy-lang.org/) in strict mode
- **Pre-commit hooks:** `pre-commit install` runs both automatically on commit

```bash
ruff check src tests
mypy src
```

## Opening a Pull Request

1. Fork the repo and branch from `main`
2. Keep PRs focused on a single concern
3. Add or update tests for changed behavior
4. Ensure `pytest`, `ruff check`, and `mypy` all pass
5. Write a clear title and description

## Reporting Issues

Open a GitHub issue with: what you expected vs. what happened, steps to reproduce, Python version and OS.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under AGPL-3.0-or-later.
