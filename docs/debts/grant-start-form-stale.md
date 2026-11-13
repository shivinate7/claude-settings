# Lane start templates show the old Grant form

**What.** Three files show the lane start line as `Grant: <owner words>, <time>`. That form is right for a `create_session` start, which the relay rule does not judge. Once PR #3038 (the relayed-grant change, branch `pwr-grant-carries-words`) merges, a `send_message` brief copied from these files is refused by rule `relay-grant-words` (a relayed grant quotes the owner's exact words). Harm: a lane or coordinator hits one needless refusal when it copies the template.

**Where.** `skills/project-ops/templates/brief.md`, line 1. `docs/decisions/session-tiers.md`, line 67, the "Lane start and effort" entry. `docs/decisions/agent-model-cap.md`, line 108, "The lane effort pin". The rule itself sits in `hooks/guard.py` on PR #3038's branch.

**Decision.** relayed-grant-read-from-page (a relayed grant counts only when the receiver reads it from the page). Its "What a relay message carries" section sets the `send_message` form. That section exists on PR #3038's branch until the PR merges.

**Retire.** Closed when a case run by `hooks/test_guard.py` finds the quoted form, `Grant: "<exact words>" (owner, <time>) covers <act>`, in the three places above for a `send_message` start, and finds that a `create_session` start keeps `Grant: <owner words>, <time>`. The case goes red on the current text first. The `create_session` form stays pinned by `tests/guard/s29666-rule9.py`.
