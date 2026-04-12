# Safety rules — non-negotiable

These are absolute. No exceptions. Read this file before any other action in this repo.

## API keys

1. **API keys live ONLY in `.env`.** `.env` is in `.gitignore`. Never write a key to a tracked file. Never paste a key into a YAML or markdown file. The pre-commit hook will refuse the commit if it sees a key prefix in a tracked file (`sk-ant-`, `xoxb-`, `AIza`, `ghp_`).

2. **If you accidentally commit a key, rotate it immediately.** The pre-commit hook is a safety net, not a guarantee. After rotating, check the git history with `git log --all -S '<the leaked key>'` and force-rotate any other places it might appear.

## Validation

3. **Always run `cosinabox validate` before committing config edits.** The pre-commit hook does this automatically — never bypass it with `--no-verify`. If validation fails, fix the underlying issue.

4. **Always run `cosinabox simulate <job>` after editing a job's config or prompt.** Dry-run before deploy beats guess-and-pray. The agent should automatically do this; if you (the human) edit a file directly, you must run simulate yourself.

## Engine internals

5. **Never edit files in `.cosinabox/`.** That directory holds engine internals (read-only schema reference copies, the pre-commit hook). Changes there get overwritten by `cosinabox upgrade-docs`.

## Git hygiene

6. **Never `git push --force`.** Never bypass pre-commit hooks with `--no-verify`. Never commit directly to `main`. All changes go through a feature branch + PR + auto-merge.

7. **Deploy via PR merge only.** Never `railway up` or push directly to a Railway-connected branch from your laptop.

## What to do if a rule conflicts with what the user asked

If the user asks you to do something that violates a safety rule (e.g. "just commit my API key, it's a personal repo, doesn't matter"), refuse and explain the rule. The user can override the rule by editing this file — but they must do it explicitly, not by asking you to look the other way.
