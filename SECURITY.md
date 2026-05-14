# Security Policy

## Supported Versions

CoSinaBox is in active 0.1.x development. Only the latest released minor version receives security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

If you discover a security issue, please **do not open a public GitHub issue**.

Use GitHub's [private vulnerability reporting](https://github.com/rovikrobert/cosinabox/security/advisories/new) — this notifies the maintainers without exposing the report.

If GitHub is unavailable, email `rovikjeremiah@gmail.com` with `[cosinabox security]` in the subject line.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce (proof-of-concept code is welcome)
- Affected version(s) and any relevant configuration
- Whether you have a suggested fix

## Response Expectations

- **Acknowledgement:** within 7 days
- **Triage and severity assessment:** within 14 days
- **Fix or mitigation:** depends on severity; critical issues prioritized

We will credit reporters in the release notes unless they request anonymity.

## Scope

Security-relevant areas of cosinabox:

- OAuth token handling (Google refresh tokens, Telegram bot tokens)
- Anthropic API key handling
- The `consult` MCP endpoint when exposed over HTTP
- Tool calls that touch external services (Gmail send, Calendar mutate)
- Anything that ships secrets to logs, telemetry, or third parties

Out of scope:

- Issues in third-party dependencies (report upstream first)
- Vulnerabilities requiring local OS access to a user's machine
- Misuse of API keys after they've been disclosed by the user
