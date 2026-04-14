# Policy engine — approval gates

Your CoS has a policy engine that controls which actions it can take without asking. This prevents accidental email sends, event creation, or other write operations.

## Default behavior

| Action | Policy | Why |
|--------|--------|-----|
| Search email, read calendar, CRM lookup, web search, meeting transcripts | **Auto-allowed** | Read-only, no side effects |
| Compose email draft | **Auto-allowed** | Drafts don't send — you review in Gmail first |
| Send email (`gmail_send`) | **Requires approval** | Sends on your behalf — you must confirm |
| Create calendar event | **Requires approval** | Books your time — you must confirm |
| Unknown / new tools | **Requires approval** | Safe default |

## How approval works

1. The CoS proposes an action: "I've drafted a reply to Alice. Want me to send it?"
2. You reply with a confirmation: **yes**, **go ahead**, **approved**, **do it**, **send it**, **ok**, **sure**
3. The CoS executes the action

If you don't approve, the action is not taken. Approvals expire after 2 minutes.

## Customizing rules

Add `policy_rules` to your `integrations.yaml` to override defaults:

```yaml
integrations:
  # ... existing integrations ...
  policy_rules:
    # Auto-approve emails to your own domain
    - tool_pattern: "gmail_send"
      action: allow
      condition_field: to
      condition_op: contains
      condition_value: "@yourcompany.com"
      priority: 50
      description: "Auto-approve internal emails"

    # Block emails to a sensitive domain
    - tool_pattern: "gmail_compose"
      action: deny
      condition_field: to
      condition_op: contains
      condition_value: ".gov"
      priority: 10
      description: "Government emails require manual handling"
```

### Rule fields

| Field | Required | Description |
|-------|----------|-------------|
| `tool_pattern` | Yes | Tool name or glob pattern (e.g., `gmail_*`, `calendar_create_event`) |
| `action` | Yes | `allow`, `deny`, or `require_approval` |
| `condition_field` | No | Field in tool input to check (e.g., `to`, `attendees`) |
| `condition_op` | No | Operator: `contains`, `not_contains`, `eq`, `neq` |
| `condition_value` | No | Value to compare against |
| `priority` | No | Lower number = higher priority (default: 50). Default rules are 60-200. |
| `description` | No | Human-readable explanation |

### Priority guide

- **1-30**: Protected rules (always enforced, even for the owner)
- **50**: Custom overrides (default for user rules)
- **60**: Default write gates (gmail_send, calendar_create_event)
- **200**: Default read allows
- **999**: Catch-all (unknown tools require approval)

Custom rules with priority < 60 override the default gates. Rules with priority > 200 are evaluated after the default allows.
