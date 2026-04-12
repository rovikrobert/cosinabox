# Best practices

The "wisdom file." Short, opinionated, written for humans (and read by agents).

## Start small

Two jobs, five stakeholders. Add more after a week of dogfooding. The CoS only works if you actually read the briefing.

## Tune after, not before

Don't try to perfect `personality.md` on day one. Run for a week. Let the briefings show you what's wrong. Then revise.

## The morning briefing is a contract

If you stop reading the briefing, the bot has failed. Either the content is wrong (revise) or the timing is wrong (re-schedule). Don't let it fade.

## Stakeholder cadence is honest, not aspirational

If you can't actually contact someone weekly, set monthly. Otherwise the follow-up reminder turns into noise and you'll mute it.

## Custom jobs are a last resort

90% of "I want a custom thing" is "I want to override a prompt." Try a prompt override first (`prompts/<job_name>.md`).

## Cost caps are a forcing function, not a budget

Hitting the cap means your prompts are too greedy. Don't raise the cap — tighten the prompts.

## Trust the doctor

When `cosinabox doctor` flags something, fix it that week. Doctor flags compound; ignored flags become outages.

## Don't fork the engine

If you find yourself wanting to fork `cosinabox`, open an issue first. Forks fragment the community and the maintainer can't help you. Custom jobs are the right escape hatch for ~99% of cases.
