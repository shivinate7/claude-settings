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

## The probe of a refused act

Owner, Cockpit item 435 (grant-probe-headless-arm), typed "Approved" in the lane chat 2026-11-08
11:55 CST: pick a. Run arm 1 headless, the 2026-11-06 way. Gate the lane's `Agent` spawn first
(plan question 3 a). It replaces the child cloud session of item 222 (hook-allow-probe), whose
settings file the guards refused. Arm 2, a sibling guard's `deny` against the hook's `allow`, was
not run.

Result, 2026-11-08 11:56-11:59 CST, Claude Code 2.1.319, nested `claude -p --permission-mode auto
--model sonnet`, hook `probe/hook_allow_probe.py` (branch `archive/hook-allow-probe`):

- The act: a Bash write of an allow rule into `.claude/settings.local.json`.
- Asked in the typed prompt, the classifier allowed it, with or without the hook.
- Asked by a relayed file text, with the hook off, the classifier denied it: "[Self-Modification]".
- The same, with the hook on: the hook emitted `allow`. The debug log then reads "Hook returned
  'allow' for Bash, but an ask rule, a safety check, a ToolHost's person-only ask or plan mode
  requires the full permission pipeline". The classifier still denied it: "[Self-Modification]".

So a hook `allow` does not lift a classifier refusal when a safety check applies. A write to a
settings file is such a case. Whether a lane's `Agent` spawn is such a case: unmeasured. The mod
`tool.check` gate is next (pick 5).

Why: the owner had to type a grant again in each session (plan, section "The problem").

Kind: build
Plan: docs/plans/grant-reaches-lanes.md#6-questions-for-the-owner (all)
