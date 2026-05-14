# cosinabox

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Open-source Chief of Staff in a box. Opinionated, proactive, runs on your own infra.

CoSinaBox is a self-hosted AI Chief of Staff agent that runs your day. Out of the box: morning briefing, pre-meeting prep, evening wrap, weekly review, follow-up tracking. Optional jobs cover urgent-email triage, meeting-transcript extraction, CRM sync, and multi-person scheduling. You configure *who it's for*, not *what it does*.

## Key Features

- **13 built-in jobs:** daily briefings (morning / evening / weekly), pre- and post-meeting prep, follow-up nudges, urgent-email alerts, meeting-transcript extraction, CRM sync, multi-person scheduling, OAuth health monitoring
- **Telegram-first:** primary interface via Telegram bot
- **Google integration:** Calendar, Gmail, Drive (optional)
- **SQLite memory:** persistent context without external databases
- **Zero telemetry:** runs entirely on your infra with your API keys
- **Extensible:** add custom jobs via a thin user repo

## Prerequisites

- Python 3.11+
- [Anthropic API key](https://console.anthropic.com/) (Claude powers the agent)
- Telegram bot token (via [@BotFather](https://t.me/botfather))
- Optional: Google OAuth credentials (for Calendar/Gmail/Drive)
- Optional: Fireflies API key (for meeting transcripts)

## Quickstart

```bash
# Install the engine
pip install cosinabox

# Scaffold your user repo
cosinabox init my-cos
cd my-cos

# Configure (edit .env with your API keys, then customize personality.md)
cp .env.example .env
$EDITOR .env
$EDITOR personality.md

# Verify setup
cosinabox doctor

# Run
cosinabox run
```

## Development Setup

```bash
# Clone and install in dev mode
git clone https://github.com/rovikrobert/cosinabox.git
cd cosinabox
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,google,fireflies,search,attio]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Lint & type-check
ruff check src tests
mypy src
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development guidelines.

## Project Structure

```
cosinabox/
├── src/cosinabox/
│   ├── agent/         # Claude API loop, routing, cost tracking
│   ├── app/           # App orchestrator (config, tools, jobs, alerts, chat)
│   ├── bot/           # Telegram adapter
│   ├── cli/           # CLI commands (init, run, doctor)
│   ├── jobs/          # 13 built-in jobs
│   ├── memory/        # SQLite persistence layer
│   ├── scheduling/    # APScheduler integration
│   ├── tools/         # External integrations (Google, Fireflies, Serper)
│   ├── prompts/       # Default prompt templates
│   ├── personas/      # Persona templates
│   ├── schemas/       # JSON schemas for config validation
│   └── templates/     # User-repo scaffold (used by `cosinabox init`)
├── tests/
│   ├── unit/          # Unit tests
│   └── stress/        # Stress/integration tests
└── docs/              # Architecture and design docs
```

## Architecture

CoSinaBox follows an **engine + thin user repo** pattern (similar to Hugo + content, or Next.js + app code):

- **Engine** (`cosinabox` package): the agent loop, scheduling, tools, and built-in jobs
- **User repo** (scaffolded by `cosinabox init`): your personality, stakeholders, integrations config, and optional custom jobs

For detailed architecture, see [docs/specs/2026-04-11-cosinabox-design.md](docs/specs/2026-04-11-cosinabox-design.md).

## Privacy

- Zero telemetry by default -- no data leaves your machine except to APIs you explicitly configure
- AGPL-3.0 license to protect against SaaS extraction without contribution
- README documents every external service the engine touches

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=cosinabox
```

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
