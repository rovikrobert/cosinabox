# Proactive suggestions

These aren't rules — they're patterns the agent should notice and surface to the user without being asked. Good agents are proactive but not noisy. The threshold for surfacing should be: *"Would the user thank me for noticing?"*

## After 2 weeks of usage

- If `followup_reminder` is still disabled and `stakeholders.yaml` has 5+ entries with stale `last_contact` dates, suggest enabling it.
- If `weekly_review` is disabled, suggest enabling it for next Friday.

## When the user mentions a missed meeting

- Check whether `pre_meeting_prep` is enabled in `jobs.yaml`. If not, suggest enabling it.
- If it's enabled but didn't fire for the meeting in question, run `cosinabox doctor` and surface `prep_noise` (filter overly aggressive) or `oauth_expiring` (auth token broken).

## When the user complains the briefing is wrong

- Recommend a **prompt override** (`prompts/morning_briefing.md`) over editing `personality.md` — overrides are more surgical and less likely to break other jobs.
- If the issue is "wrong stakeholder context", recommend updating `stakeholders.yaml` instead.
- If the issue is "wrong tone", recommend the persona interview to revise voice.

## When `cosinabox doctor` flags something

- Surface the flag immediately. Don't wait until the next session.
- If `cost_runaway` fires: surface the daily spend, suggest a tighter cap, suggest tightening prompts.
- If `secret_in_tracked_file` fires: STOP. This is a security incident. Walk the user through key rotation immediately.
- If `oauth_expiring` fires: walk the user through `cosinabox auth google` again.

## When the user adds a stakeholder

- Confirm cadence is realistic, not aspirational. "Can you actually contact this person weekly?" If no, suggest monthly.

## When the user asks for a custom job

- Push back. 90% of the time the answer is a prompt override. Read `docs/agent/adding-custom-jobs.md` to the user before writing Python.

## What NOT to surface proactively

- Cost numbers below the cap. (Daily spend is interesting only if it's hot.)
- Routine job successes. ("Morning briefing fired at 8:00am" is not a notification.)
- Doctor flags that resolve themselves.

Be helpful. Don't be a pager.
