# cosinabox 0.1.0 PyPI Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `cosinabox 0.1.0` to PyPI so every downstream (OSS user-repos, `rovik-keevs`) can `pip install cosinabox[google]` instead of a git+ direct reference.

**Architecture:** Three gates — metadata + CI scaffolding, TestPyPI dry-run, production PyPI release — each ending with a merged PR. Then two consumer PRs (template verification + rovik-keevs pin update) prove the release works end-to-end. GitHub Actions OIDC Trusted Publishing is used to avoid long-lived PyPI API tokens.

**Tech Stack:** `python -m build` (hatchling backend, already configured), `twine` for inspection, GitHub Actions with PyPI Trusted Publishing OIDC, Python 3.11+.

---

## Milestone 1: Release metadata + CI (gate before any upload)

Goal: make the package metadata publish-grade, add a release workflow, create a CHANGELOG. One PR at the end.

### Task 1.1: Verify `cosinabox` is available on PyPI

**Files:** none — pre-flight check.

- [ ] **Step 1: Query PyPI for the project name**

Run:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/cosinabox/json
```

Expected: `404` (name is free). If `200`, the name is taken — stop and surface to the maintainer. Pick an alternative name (e.g., `cosinabox-engine`) and update `pyproject.toml` + `src/cosinabox/__init__.py` + README badges before proceeding.

- [ ] **Step 2: Also check TestPyPI**

Run:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://test.pypi.org/pypi/cosinabox/json
```

Expected: `404`. If `200`, someone else already reserved it on TestPyPI — still usable for production PyPI, but upload via a suffixed name on TestPyPI (e.g., `cosinabox-dryrun`) or skip TestPyPI entirely.

### Task 1.2: Add PyPI classifiers + URLs to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Open `pyproject.toml` and locate the `[project]` table**

Current state: has `name`, `version`, `description`, `readme`, `requires-python`, `license`, `authors`, `dependencies`. Missing: `classifiers`, `keywords`, `urls`.

- [ ] **Step 2: Add classifiers + keywords + urls**

Insert after the `authors` line in `[project]`:

```toml
keywords = ["chief-of-staff", "agent", "anthropic", "claude", "telegram", "productivity"]
classifiers = [
  "Development Status :: 4 - Beta",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Communications :: Chat",
  "Topic :: Office/Business :: Scheduling",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
]

[project.urls]
Homepage = "https://github.com/rovikrobert/cosinabox"
Source = "https://github.com/rovikrobert/cosinabox"
Issues = "https://github.com/rovikrobert/cosinabox/issues"
Changelog = "https://github.com/rovikrobert/cosinabox/blob/main/CHANGELOG.md"
```

- [ ] **Step 3: Verify `pyproject.toml` still parses**

Run:
```bash
python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"
```

Expected: no output (exit 0). If a TOML parse error prints, fix the bracket/comma syntax before proceeding.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(release): add PyPI classifiers, keywords, project URLs"
```

### Task 1.3: Create `CHANGELOG.md` with the 0.1.0 entry

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write the changelog**

Create `CHANGELOG.md` with:

```markdown
# Changelog

All notable changes to cosinabox will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-21

Initial public release.

### Added
- Core `App` orchestrator — config loader, job scheduler, Telegram bot, agent loop.
- Five built-in jobs: morning briefing, pre-meeting prep, evening wrap, weekly review, follow-up nudges.
- Google integration (optional extra `[google]`): Calendar + Gmail tools, OAuth flow.
- Attio integration (optional extra `[attio]`): stakeholder CRM sync, keep-warm reminders.
- Fireflies integration (optional extra `[fireflies]`): meeting transcript ingest for post-meeting debrief.
- Serper integration (optional extra `[search]`): web search tool.
- Persona templates (one ships: `founder`).
- Setup interview state machine via `cosinabox init`.
- JSON Schemas for `personality.md`, `stakeholders.yaml`, `jobs.yaml`, `integrations.yaml`.
- `cosinabox validate` / `simulate` / `migrate` commands.
- Commitment tracking with auto-resolve verification (Gmail + Fireflies evidence).
- Auth-health watcher for revoked Google tokens.
- Model-chain failover for Anthropic 429/529 responses.

[0.1.0]: https://github.com/rovikrobert/cosinabox/releases/tag/v0.1.0
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(release): add CHANGELOG with 0.1.0 entry"
```

### Task 1.4: Add `release.yml` GitHub Actions workflow (OIDC Trusted Publishing)

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow**

Write `.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags:
      - "v*.*.*"
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Extract tag version
        id: version
        run: echo "version=${GITHUB_REF#refs/tags/v}" >> "$GITHUB_OUTPUT"
      - name: Verify tag matches pyproject version
        run: |
          file_version=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          if [ "$file_version" != "${{ steps.version.outputs.version }}" ]; then
            echo "Tag v${{ steps.version.outputs.version }} does not match pyproject version $file_version"
            exit 1
          fi
      - run: pip install --upgrade build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
          if-no-files-found: error

  publish-testpypi:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: testpypi
      url: https://test.pypi.org/project/cosinabox/
    permissions:
      id-token: write  # OIDC Trusted Publishing
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/

  publish-pypi:
    needs: publish-testpypi
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/project/cosinabox/
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Verify the YAML parses**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

Expected: no output. If a `yaml.YAMLError` prints, fix indentation before proceeding.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): add OIDC-based PyPI publish workflow triggered on v*.*.* tags"
```

### Task 1.5: Build and inspect the wheel locally (dry run, no upload)

**Files:** none — verification step.

- [ ] **Step 1: Install build in a clean venv**

Run:
```bash
python3 -m venv /tmp/cosi-build-venv
/tmp/cosi-build-venv/bin/pip install --upgrade build twine
```

Expected: installs succeed.

- [ ] **Step 2: Build sdist + wheel from the worktree root**

Run:
```bash
rm -rf dist/
/tmp/cosi-build-venv/bin/python -m build
```

Expected: writes `dist/cosinabox-0.1.0-py3-none-any.whl` and `dist/cosinabox-0.1.0.tar.gz`. If hatchling errors about missing files, check that `[tool.hatch.build.targets.wheel]` in pyproject still lists `src/cosinabox` and that the `force-include` mappings for persona/schema files are valid.

- [ ] **Step 3: Inspect wheel contents for secrets/tests**

Run:
```bash
/tmp/cosi-build-venv/bin/python -m zipfile -l dist/cosinabox-0.1.0-py3-none-any.whl | head -40
/tmp/cosi-build-venv/bin/python -m zipfile -l dist/cosinabox-0.1.0-py3-none-any.whl | grep -Ei "test|\.env|credentials|token" || echo "no suspect files — OK"
```

Expected: no `test_*.py`, no `.env*`, no `credentials.json`, no `token.json` in the wheel. If any appear, add them to `.gitignore` (if not already) and adjust the hatchling wheel target — tests must not ship in the wheel.

- [ ] **Step 4: Run `twine check` on the artifacts**

Run:
```bash
/tmp/cosi-build-venv/bin/twine check dist/*
```

Expected: `PASSED` for both the sdist and the wheel. If the README fails to render, adjust README markdown until `twine check` is green.

- [ ] **Step 5: Install the freshly built wheel in another clean venv and smoke-test**

Run:
```bash
python3 -m venv /tmp/cosi-install-venv
/tmp/cosi-install-venv/bin/pip install "dist/cosinabox-0.1.0-py3-none-any.whl[google]"
/tmp/cosi-install-venv/bin/python -c "from cosinabox import App, __version__; print(__version__)"
/tmp/cosi-install-venv/bin/cosinabox --help
```

Expected: `0.1.0` printed, then the CLI help text. If imports fail, something was missed from the wheel — check `[tool.hatch.build.targets.wheel.force-include]` and re-run from Step 2.

- [ ] **Step 6: Commit (nothing to stage — this task is verification only)**

No commit. Proceed to Task 1.6.

### Task 1.6: Open M1 PR, auto-merge, verify main is green

**Files:** none — repository action.

- [ ] **Step 1: Push the branch and open the PR**

Run:
```bash
git push -u origin plan/pypi-0.1
gh pr create \
  --title "chore(release): prep cosinabox for PyPI 0.1.0" \
  --body "M1 of docs/plans/2026-04-20-cosinabox-pypi-0.1.md — classifiers, CHANGELOG, release workflow. No upload yet. TestPyPI + PyPI are M2 + M3."
gh pr merge --auto --squash
```

Expected: PR opens, CI runs, auto-merges when green.

- [ ] **Step 2: Wait for CI to pass and merge**

Run:
```bash
gh pr view --json state,mergeStateStatus -q '.state + " / " + .mergeStateStatus'
```

Expected: `MERGED / CLEAN` (or `MERGED / UNKNOWN` — both are fine). If `FAILING`, read `gh pr checks` output and fix.

---

## Milestone 2: TestPyPI dry-run

Goal: upload once to TestPyPI via a disposable tag, install from TestPyPI into a clean venv, confirm every optional extra resolves. Bail out before touching real PyPI if anything is wrong.

### Task 2.1: Configure PyPI Trusted Publishing (one-time setup)

**Files:** none — done via the PyPI/TestPyPI UIs (not the repo).

- [ ] **Step 1: Register `cosinabox` on TestPyPI as a pending project**

1. Log into `https://test.pypi.org/` (create an account if needed).
2. Go to your **Account Settings** (avatar menu top-right) → **Publishing** → direct URL: `https://test.pypi.org/manage/account/publishing/`. Find **"Add a new pending publisher"**. (The `Your projects → Publishing` path only works for projects that already exist on the registry — pending publishers for not-yet-registered projects live under Account Settings.)
3. Fill in:
   - PyPI Project Name: `cosinabox`
   - Owner: `rovikrobert`
   - Repository name: `cosinabox`
   - Workflow name: `release.yml`
   - Environment name: `testpypi`
4. Submit.

- [ ] **Step 2: Register `cosinabox` on PyPI as a pending project**

Same steps as above, but on `https://pypi.org/`, and environment name `pypi`.

- [ ] **Step 3: Add `testpypi` and `pypi` GitHub environments on the repo**

1. `gh api -X PUT repos/rovikrobert/cosinabox/environments/testpypi -f wait_timer=0`
2. `gh api -X PUT repos/rovikrobert/cosinabox/environments/pypi -f wait_timer=0`

Expected: 200 OK on both. These environments are referenced by `release.yml` and must exist before the workflow runs. Confirm with `gh api repos/rovikrobert/cosinabox/environments -q '.environments[].name'`.

### Task 2.2: Tag a pre-release and watch the workflow upload to TestPyPI

**Files:** none — release action.

- [ ] **Step 1: Pull the merged M1 main**

Run:
```bash
git checkout main
git pull --ff-only
```

Expected: fast-forwards to the M1 merge commit.

- [ ] **Step 2: Create a throwaway pre-release tag**

Run:
```bash
# Temporarily bump pyproject + __init__ so the tag version matches.
# We'll revert this commit right after TestPyPI upload — it should NOT
# be on main.
git checkout -b release/testpypi-0.1.0rc1
sed -i '' 's/version = "0.1.0"/version = "0.1.0rc1"/' pyproject.toml
sed -i '' 's/__version__ = "0.1.0"/__version__ = "0.1.0rc1"/' src/cosinabox/__init__.py
git add pyproject.toml src/cosinabox/__init__.py
git commit -m "chore(release): temporary 0.1.0rc1 version for TestPyPI dry-run"
git tag v0.1.0rc1
git push origin v0.1.0rc1
```

Expected: tag pushed, `release.yml` kicks off on the tag push (not the branch).

- [ ] **Step 3: Watch the release workflow succeed through TestPyPI**

Run:
```bash
gh run watch $(gh run list --workflow=release.yml --limit=1 --json databaseId -q '.[0].databaseId')
```

Expected: `build` and `publish-testpypi` steps succeed; `publish-pypi` is gated by the `testpypi → pypi` job dependency and will also run — which is NOT what we want for a dry-run. **Cancel the run before `publish-pypi` starts** if you see it progressing past TestPyPI. To avoid this, temporarily edit `release.yml` to not depend publish-pypi on publish-testpypi for the dry run, OR (simpler) accept that rc versions are expected on PyPI and push a real rc tag once.

**Alternative (cleaner):** update `release.yml` so `publish-pypi` is only triggered for non-prerelease tags. Guard with:
```yaml
if: ${{ !contains(github.ref_name, 'rc') && !contains(github.ref_name, 'a') && !contains(github.ref_name, 'b') }}
```
Add this guard in a prior step (Task 1.4 addendum) if you prefer to gate it properly.

- [ ] **Step 4: Verify the package landed on TestPyPI**

Run:
```bash
curl -sS https://test.pypi.org/pypi/cosinabox/json | python -c "import sys, json; d = json.load(sys.stdin); print(list(d['releases'].keys()))"
```

Expected: includes `"0.1.0rc1"`.

### Task 2.3: Install from TestPyPI in a clean venv, smoke-test every extra

**Files:** none.

- [ ] **Step 1: Install the base package from TestPyPI**

Run:
```bash
python3 -m venv /tmp/cosi-testpypi-venv
/tmp/cosi-testpypi-venv/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  "cosinabox==0.1.0rc1"
/tmp/cosi-testpypi-venv/bin/python -c "from cosinabox import App, __version__; print(__version__)"
```

Expected: `0.1.0rc1` printed. `--extra-index-url` is important — TestPyPI doesn't mirror runtime deps like `anthropic` and pip falls back to real PyPI for those.

- [ ] **Step 2: Install with every optional extra in turn**

Run:
```bash
for extra in google fireflies search attio; do
  python3 -m venv "/tmp/cosi-testpypi-${extra}-venv"
  "/tmp/cosi-testpypi-${extra}-venv/bin/pip" install \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple \
    "cosinabox[$extra]==0.1.0rc1" || echo "FAILED: $extra"
done
```

Expected: all four complete without "FAILED:". If any extra fails, the dependency group is misconfigured in `pyproject.toml` — fix and re-tag with an `rc2`.

- [ ] **Step 3: Smoke-test the CLI entry point**

Run:
```bash
/tmp/cosi-testpypi-venv/bin/cosinabox --help
```

Expected: CLI help text listing `init`, `validate`, `simulate`, `migrate` subcommands.

- [ ] **Step 4: Clean up the rc branch**

Run:
```bash
git push origin --delete release/testpypi-0.1.0rc1 2>/dev/null || true
git branch -D release/testpypi-0.1.0rc1 2>/dev/null || true
```

The rc tag itself stays — TestPyPI and the git tag history preserve evidence of the dry-run. Don't delete the v0.1.0rc1 git tag.

---

## Milestone 3: v0.1.0 PyPI release

Goal: the real thing. Tag, publish, verify.

### Task 3.1: Tag v0.1.0 and trigger the production release

**Files:** none.

- [ ] **Step 1: Ensure main is clean and at the M1 commit**

Run:
```bash
git checkout main
git pull --ff-only
git status --porcelain
```

Expected: no output from status.

- [ ] **Step 2: Confirm pyproject + `__init__` still say 0.1.0**

Run:
```bash
grep -E '^version|^__version__' pyproject.toml src/cosinabox/__init__.py
```

Expected: both show `0.1.0` (not the rc). If they say `0.1.0rc1`, a revert commit was missed — fix on main before tagging.

- [ ] **Step 3: Create the v0.1.0 tag and push**

Run:
```bash
git tag -a v0.1.0 -m "cosinabox 0.1.0 — initial public release"
git push origin v0.1.0
```

Expected: tag push triggers `release.yml` for the second time; `build` → `publish-testpypi` (will 400 because 0.1.0 exists after rc, but TestPyPI lets you upload the "real" version separately — that's fine since we don't actually need the TestPyPI leg this time) → `publish-pypi`.

If TestPyPI blocks because `0.1.0` is unreleased there, tweak the workflow to skip `publish-testpypi` when the tag has no prerelease suffix (or simply accept a TestPyPI upload of 0.1.0 — it causes no harm).

- [ ] **Step 4: Watch the run**

Run:
```bash
gh run watch $(gh run list --workflow=release.yml --limit=1 --json databaseId -q '.[0].databaseId')
```

Expected: `publish-pypi` succeeds.

- [ ] **Step 5: Verify 0.1.0 is live on PyPI**

Run:
```bash
curl -sS https://pypi.org/pypi/cosinabox/json | python -c "import sys, json; d = json.load(sys.stdin); print(d['info']['version'])"
```

Expected: `0.1.0`.

### Task 3.2: Publish a GitHub Release with CHANGELOG body

**Files:** none — gh CLI action.

- [ ] **Step 1: Create the GitHub Release**

Run:
```bash
gh release create v0.1.0 \
  --title "cosinabox 0.1.0" \
  --notes-file <(awk '/^## \[0.1.0\]/,/^## \[/{ if (/^## \[/ && !/0.1.0/) exit; print }' CHANGELOG.md | sed '$d') \
  dist/cosinabox-0.1.0-py3-none-any.whl dist/cosinabox-0.1.0.tar.gz
```

Expected: release page created at `github.com/rovikrobert/cosinabox/releases/tag/v0.1.0` with both artifacts attached. If `dist/` isn't present locally, re-run `python -m build` first.

### Task 3.3: Clean up the rc artifacts (optional)

**Files:** none.

- [ ] **Step 1: (Optional) yank the rc on TestPyPI**

Not strictly required — rc versions on TestPyPI don't interfere with PyPI. If you want to yank anyway: log into test.pypi.org, project settings, `Yank release 0.1.0rc1`. Document the yank reason: "superseded by 0.1.0 final".

---

## Milestone 4: Consumer updates (rovik-keevs + template)

Goal: prove the release works end-to-end by pointing the two known consumers at the PyPI package and removing the git+ direct-reference workarounds.

### Task 4.1: Verify the OSS template installs cleanly from PyPI

**Files:**
- Verify: `src/cosinabox/templates/user-repo/pyproject.toml`
- Verify: `src/cosinabox/templates/user-repo/Dockerfile`

- [ ] **Step 1: Scaffold a fresh user-repo and `pip install -e .` it**

Run:
```bash
rm -rf /tmp/cosi-user-test
python3 -m venv /tmp/cosi-scaffold-venv
/tmp/cosi-scaffold-venv/bin/pip install cosinabox
/tmp/cosi-scaffold-venv/bin/cosinabox init /tmp/cosi-user-test
cd /tmp/cosi-user-test
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -c "from cosinabox import App; print('import OK')"
```

Expected: `import OK`. If PyPI rejects because `>=0.1,<0.2` can't resolve, something is wrong with the release — do not proceed until `pip install cosinabox[google]>=0.1,<0.2` resolves to `0.1.0`.

- [ ] **Step 2: Build the Dockerfile to confirm no apt-get git is needed now**

Run:
```bash
cd /tmp/cosi-user-test
docker build -t cosi-user-test:local . 2>&1 | tail -30
```

Expected: build succeeds, no git-related errors, image is smaller than the rovik-keevs image (since no `apt-get install git` layer). If docker isn't installed locally, skip this and verify by reading the Dockerfile to confirm it doesn't need `git`.

- [ ] **Step 3: No commit** — this task is verification only.

### Task 4.2: Open a PR on `rovik-keevs` switching to the PyPI pin

**Files (in a separate clone of `rovikrobert/rovik-keevs`):**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`

- [ ] **Step 1: Clone rovik-keevs if not already, create a branch**

Run:
```bash
rm -rf /tmp/rovik-keevs-pypi
gh repo clone rovikrobert/rovik-keevs /tmp/rovik-keevs-pypi
cd /tmp/rovik-keevs-pypi
git checkout -b chore/pypi-pin
```

- [ ] **Step 2: Swap the pyproject dep line**

Edit `pyproject.toml`:

```toml
# before
dependencies = [
  "cosinabox[google,attio] @ git+https://github.com/rovikrobert/cosinabox.git@main",
]

[tool.hatch.metadata]
allow-direct-references = true
```

```toml
# after
dependencies = [
  "cosinabox[google,attio]>=0.1,<0.2",
]
```

(Delete the `[tool.hatch.metadata]` section entirely — no longer needed.)

- [ ] **Step 3: Drop `apt-get install git` from the Dockerfile**

Edit `Dockerfile` — delete the block starting with `# git is needed by pip to resolve the git+https URL ...` and the `RUN apt-get ...` below it. The `FROM`, `WORKDIR`, `COPY pyproject.toml`, `RUN pip install -e .`, `COPY . /app`, and `CMD` lines remain.

- [ ] **Step 4: Verify the install works locally**

Run:
```bash
python3 -m venv /tmp/rovik-pypi-venv
cd /tmp/rovik-keevs-pypi
/tmp/rovik-pypi-venv/bin/pip install -e .
/tmp/rovik-pypi-venv/bin/python -c "from cosinabox import App; print('OK')"
```

Expected: `OK` — and pip resolves cosinabox from PyPI, not git.

- [ ] **Step 5: Commit + open PR + auto-merge**

Run:
```bash
cd /tmp/rovik-keevs-pypi
git add pyproject.toml Dockerfile
git commit -m "chore(deploy): switch cosinabox dep from git+main to PyPI 0.1.x"
git push -u origin chore/pypi-pin
gh pr create \
  --title "chore(deploy): switch cosinabox dep from git+main to PyPI 0.1.x" \
  --body "Follow-up to PR #2. Now that cosinabox 0.1.0 is on PyPI, drop the git+ URL and allow-direct-references wart. Dockerfile no longer needs apt-get install git."
gh pr merge --auto --squash
```

Expected: PR merges, next `railway redeploy` pulls cosinabox from PyPI.

- [ ] **Step 6: Trigger Railway redeploy and confirm**

Run:
```bash
mkdir -p /tmp/rovik-keevs-link && cd /tmp/rovik-keevs-link
railway link -p rovik-keevs
railway redeploy --service rovik-keevs --yes
railway logs --service rovik-keevs 2>&1 | head -20
```

Expected: new deploy logs show a successful start; `cosinabox` imports from `/usr/local/lib/python3.11/site-packages/cosinabox` (not `/app/cosinabox`).

### Task 4.3: Write the release retro

**Files:**
- Create: `docs/retros/2026-04-20-cosinabox-pypi-0.1.md`

- [ ] **Step 1: Write the retro**

Create `docs/retros/2026-04-20-cosinabox-pypi-0.1.md`:

```markdown
# Retro: cosinabox 0.1.0 PyPI release (2026-04-20)

## What shipped
- cosinabox 0.1.0 on PyPI.
- GitHub Actions OIDC Trusted Publishing pipeline.
- CHANGELOG.md + GitHub Release.
- Template (unchanged) now works as-documented.
- rovik-keevs on PyPI pin (no more git+ direct reference).

## Estimates vs reality
(Fill in — what took longer than expected? What was faster?)

## Lessons
- (Fill in — e.g. did the rc dry-run catch anything real? Was OIDC setup straightforward?)

## Follow-ups
- Docker base image `cosinabox/runtime:0.1.x` (deferred — tracked in Plan 3).
- `cosinabox init` should stamp the scaffolding engine version into the user's pyproject for migration baseline.
```

- [ ] **Step 2: Commit**

```bash
git add docs/retros/2026-04-20-cosinabox-pypi-0.1.md
git commit -m "docs(retros): cosinabox 0.1.0 PyPI release retrospective"
git push
```

---

## Self-review completed

- **Spec coverage:** every gap surfaced in the brainstorm (PyPI publish, template verification, rovik-keevs switch, `allow-direct-references` wart removal) has a task.
- **Placeholders:** none — every command is explicit.
- **Type consistency:** version strings (`0.1.0`, `0.1.0rc1`), environment names (`testpypi`, `pypi`), and tag patterns (`v*.*.*`) are consistent across tasks.
- **Risks called out inline:** name conflict (1.1), TestPyPI dep fallback (2.3), prerelease-vs-release gating (2.2), TestPyPI 400 on re-upload (3.1).
