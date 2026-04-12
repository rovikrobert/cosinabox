# Adding custom jobs

**Custom jobs are a last resort.** 90% of "I want a custom thing" is "I want to override a prompt." Try these in order:

1. **Edit `personality.md`** — for behavior changes.
2. **Drop a `prompts/<job_name>.md` file** — for tone or format overrides on built-in jobs.
3. **Tweak `jobs.yaml`** — for schedule, filter, or threshold changes.
4. **Custom job in `custom_jobs/<name>.py`** — only if none of the above work.

## Test-first

If you do need a custom job, **write the test before the job**.

```bash
mkdir -p custom_jobs tests
```

Example structure:

```python
# tests/test_my_custom_job.py
from __future__ import annotations

from custom_jobs.my_custom_job import MyCustomJob


def test_my_custom_job_returns_string():
    job = MyCustomJob()
    result = job.run(stakeholders=[])
    assert isinstance(result, str)
```

```python
# custom_jobs/my_custom_job.py
from __future__ import annotations

from cosinabox.jobs.base import Job, JobContext


class MyCustomJob(Job):
    name = "my_custom_job"

    def run(self, context: JobContext) -> str:
        return "Hello from my custom job."
```

Run:

```bash
cosinabox test
cosinabox simulate my_custom_job
```

## Auto-discovery

Custom jobs in `custom_jobs/*.py` are auto-discovered at startup. The class must extend `cosinabox.jobs.base.Job` and have a unique `name` attribute. If you add a custom job and it doesn't appear, run `cosinabox describe` and look for it in the "loaded custom jobs" section.

## Risk

Custom jobs run **dynamic Python you wrote**. There is no sandbox. Don't paste code from the internet without reading it. Don't import secrets in custom jobs (use env vars). Single-user self-hosted only — never share custom jobs with strangers.

## After deploying a custom job

```bash
cosinabox doctor --json
```

Look for unexpected entries. If your custom job blew the cost cap, the doctor will surface `cost_runaway`.
