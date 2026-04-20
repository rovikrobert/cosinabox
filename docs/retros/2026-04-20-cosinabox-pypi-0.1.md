# Retro: cosinabox 0.1.0 PyPI release (2026-04-20)

Plan: [`docs/plans/2026-04-20-cosinabox-pypi-0.1.md`](../plans/2026-04-20-cosinabox-pypi-0.1.md)

## What shipped

- `cosinabox 0.1.0` published on PyPI: https://pypi.org/project/cosinabox/0.1.0/
- GitHub Actions OIDC Trusted Publishing pipeline (`.github/workflows/release.yml`) — no long-lived PyPI API tokens anywhere.
- `CHANGELOG.md` (Keep-a-Changelog format) + `CHANGELOG` entry in project URLs.
- PyPI classifiers, keywords, homepage / source / issues / changelog URLs.
- GitHub Release at `v0.1.0` with install snippet + CHANGELOG body.
- TestPyPI dry-run tag `v0.1.0rc1` kept as evidence of the gated dry-run path.
- `rovikrobert/rovik-keevs` switched from vendored cosinabox to `cosinabox[google,attio]>=0.1,<0.2` PyPI pin (PR #2). Dockerfile no longer needs `apt-get install git`.
- OSS template (`cosinabox init`) verified end-to-end: scaffolds a user-repo whose `pip install -e .` resolves `cosinabox 0.1.0` from PyPI.

## Estimates vs reality

| Milestone | Planned | Actual | Notes |
|---|---|---|---|
| M1 (metadata + CI) | ~1 hr | ~20 min | Content was fully specified in plan; subagent dispatches reduced to mechanical paste-then-verify. |
| M2 Task 2.1 (Trusted Publisher UI) | ~5 min | ~10 min | My first instructions pointed at the wrong UI path ("Your projects → Publishing" only works for existing projects). Corrected to "Account Settings → Publishing" mid-flow. Followup: amend plan's Task 2.1 step 1 to say **Account Settings** explicitly. |
| M2 Task 2.2 (rc1 tag + watch) | ~5 min | ~5 min | Prerelease gate (`if: !contains(tag, 'rc')`) worked first time — folded into Task 1.4 upfront, which saved an edit round. |
| M2 Task 2.3 (install verification) | ~5 min | ~3 min | All four extras (`google`, `fireflies`, `search`, `attio`) installed clean on first try. |
| M3 (v0.1.0 tag + release) | ~10 min | ~5 min | Went smoothly after M2 dry-run. |
| M4 Task 4.1 (template verification) | ~5 min | ~3 min | Scaffold + install + import = end-to-end success. |
| M4 Task 4.2 (rovik-keevs switch) | ~15 min | ~10 min | Updated existing PR #2 (was using git+ as stopgap) to jump straight to PyPI pin, saving a merge round. |

Total wall time: ~60 min of focused work across the whole release.

## Lessons

- **Subagent-driven loop is overkill for mechanical paste tasks.** M1's tasks were all "copy this exact content into this file." Two-stage spec+quality review per task adds latency with near-zero bug catch. Adapted to implementer + inline diff-against-plan verification and kept moving. Would reinstate the full loop for any task with real implementation judgment.
- **`gh api -X PUT environments/<name>` with `wait_timer=0` hits a billing-plan guardrail.** The 422 error was misleading — the environment actually gets created, just without the protection rule. Fix: PUT with empty body `'{}'`.
- **Hatchling + direct URL deps needs `allow-direct-references = true`.** Caught this during the rovik-keevs switch earlier — saved us from discovering it mid-release.
- **macOS `head -n -2` doesn't work.** Used it to trim CHANGELOG footer for the GitHub release body; stripped everything. Rewrote with a here-doc.
- **The TestPyPI / PyPI pending-publisher UI path is `Account Settings → Publishing`, not `Your projects → Publishing`.** The latter only shows for already-existing projects. Plan Task 2.1 step 1 says "Your projects" — needs correcting for future releases.
- **OIDC Trusted Publishing is genuinely low-friction** once the pending-publisher forms are filled in. Zero secrets in GitHub, zero API tokens in 1Password.
- **Prerelease gate on `publish-pypi` is essential.** Without it, `v0.1.0rc1` would have leaked into production PyPI. The gate kicked in correctly: `if: !contains(github.ref_name, 'rc') && !contains('a') && !contains('b')`.

## Follow-ups

- **Docker runtime base image (`cosinabox/runtime:0.1.x`)** — deferred. Template Dockerfile still uses `python:3.11-slim` + `pip install`. Tracked in the original design spec as a Plan 3 item.
- **`cosinabox init` version stamp** — today's template is static (`cosinabox[google]>=0.1,<0.2` hard-coded). Better: have `init` write the current engine `__version__` into the user's pyproject so `cosinabox migrate` has a baseline. Low priority.
- **Plan doc fix** — Task 2.1 step 1 should say "Account Settings → Publishing" not "Your projects → Publishing".
- **CONTRIBUTING.md / author metadata audit** — `pyproject.toml` has `authors = [{ name = "Cantina" }]`. For OSS positioning we might want that to be the maintainer's name or a neutral project name. Not a 0.1.0 blocker.
- **Yank `v0.1.0rc1` on TestPyPI** — optional. RC doesn't interfere with PyPI 0.1.0, so low priority.

## Verification evidence

- PyPI listing: https://pypi.org/project/cosinabox/0.1.0/ — HTTP 200, wheel + sdist present.
- Fresh venv install: `pip install cosinabox` → `0.1.0`. `from cosinabox import App` resolves to `cosinabox.app._core`.
- rovik-keevs PR #2: merged 2026-04-20. Railway deploy triggered, status pending at retro write time.
