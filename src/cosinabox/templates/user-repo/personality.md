---
schema_version: 2
name: <YOUR NAME>
role: <YOUR ROLE>
timezone: <e.g. America/Los_Angeles>
# Optional: override the brainstorm-mode prompt used by `cosinabox consult-serve`.
# When unset, the engine default is used. Keep it sharp — brainstorm mode is for
# adversarial stress-testing, not validation. Example:
#   consult_brainstorm_override: "Argue against me from an engineering-risk perspective."
# consult_brainstorm_override: ""
---

# Voice
<Tell your CoS how to talk to you. Direct? Warm? Analytical? See docs/agent/persona-interview.md to walk through this with Claude Code.>

# Stakes
<The most important thing happening in your work over the next 6 weeks. A CoS without stakes is a chatbot.>

# Defaults
<!-- Examples of things to put here:
- Always ask before sending emails on my behalf
- Keep briefings under 300 words
- Use bullet points, not paragraphs
- When in doubt, flag it — don't decide for me
- Default to my primary email for outgoing mail
Delete these comments and replace with your own. -->
- <List any opinions you want enforced — output format, when to ask vs act, etc.>
