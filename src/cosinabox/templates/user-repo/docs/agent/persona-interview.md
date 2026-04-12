# Persona interview — 10-step setup

When the user says "set up my CoS" (or any equivalent), follow this script. **Do not improvise.** The interview is a state machine owned by the engine; you invoke `cosinabox interview` and relay one question at a time to the user, then relay the user's answer back.

## How to run it

```bash
cosinabox interview --start
```

The engine prints the next question. Show the question to the user verbatim. Wait for the user's answer. Then run:

```bash
cosinabox interview --answer "<the user's answer>"
```

Repeat until the engine prints `INTERVIEW COMPLETE`. Each step writes to the appropriate config file automatically.

## The 10 steps

1. **Identity** — name, role, company, timezone. Goes into `personality.md` frontmatter.
2. **Stakes** — *"What's the most important thing happening in your work over the next 6 weeks?"* Becomes the first paragraph of `personality.md` "# Stakes" section. **A CoS without stakes is a chatbot.**
3. **Voice** — *"Pick one: blunt / warm / analytical / formal / playful. Pick a runner-up. What's a phrase a great chief of staff has said to you that you wish you heard more often?"*
4. **Top stakeholders** — *"Name your 5 most important people right now. For each: role, cadence, anything I should know."* Writes to `stakeholders.yaml`. **Start with 5, not 50.**
5. **Calendar reality** — *"Are you back-to-back? What should pre-meeting prep skip (lunch, focus blocks, internal 1:1s)?"* Tunes `pre_meeting_prep.skip_if_calendar_title_matches`.
6. **Job staging** — *"For week 1, I'm enabling only `morning_briefing` and `pre_meeting_prep`. Sound good?"* **Stage the rollout.** Other jobs default to disabled.
7. **API keys + OAuth** — agent walks the user through Telegram BotFather + Anthropic + Google OAuth as a literal step-by-step script from `docs/agent/oauth-walkthrough.md`.
8. **Budget caps** — *"Default daily cap is $15. Want to change?"* **Set caps before going live.**
9. **First simulation** — agent runs `cosinabox simulate morning_briefing --fixture=sample` and shows the output.
10. **Deploy** — agent walks the user through Railway template button + GitHub repo connect + env var entry.

## Pushback

Each step is opinionated. If the user gives an answer that would lead to a bad CoS (e.g. "no stakes, just keep it general"), push back with a one-line explanation of the lesson. Examples:

- "A CoS without stakes is a chatbot. Even a rough sentence helps — what's the biggest thing on your mind right now?"
- "Five stakeholders is a starting point, not a limit. Adding 50 on day one means you'll never read the briefing."

Every opinion is a recommendation, not a block. The user retains override authority.

## After the interview

Run:

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary of what got configured. Then proceed to step 9 (simulation) and step 10 (deploy).
