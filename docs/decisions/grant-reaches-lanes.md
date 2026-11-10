# An owner grant typed in one session reaches the session it names

## The ruling

Owner, Cockpit item 152 (grant-plan-signoff), saved 2026-11-03 18:21 CST: pick a, sign off the
plan `docs/plans/grant-reaches-lanes.md` as written. Each of its seven questions takes the
recommended pick:

1. Gate the named act in the receiving session, before the auto-mode classifier.
2. A fixed grant word, with its act catalogue in code. No free-text grant.
3. The first catalogue is `merge <pr>` and `self-edit`.
4. `self-edit` reaches the target's agents. `merge` stays with the batch runner, never its agents.
5. Probe the `PreToolUse` hook gate first, the mod `tool.check` gate second.
6. Design A, the server-attested pointer, only. Design B only if Design A's computer probes fail.
7. Keep the cloud merge allow rule (`merge/cloud_allow.json`) until the probe shows why batch
   runner 8 was refused.

Build step 1 is a probe in one session. Nothing past it is built until the probe reads back.

Why: the owner had to type a grant again in each session (plan, section "The problem").

Kind: build
Plan: docs/plans/grant-reaches-lanes.md#6-questions-for-the-owner (all)
