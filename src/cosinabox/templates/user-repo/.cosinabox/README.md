# .cosinabox/

Engine internals. **Do not edit.**

- `pre-commit` — git hook installed by `cosinabox init`. Runs `cosinabox validate` + secret scan.
- `install-hook.sh` — bootstrap script that links the pre-commit hook into `.git/hooks/`.
- `schemas/` — read-only reference copies of the JSON Schemas. Live validation always uses the schemas from the installed `cosinabox` engine, not from this directory.

To refresh this directory after upgrading the engine, run `cosinabox upgrade-docs`.
