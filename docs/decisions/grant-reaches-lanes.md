# An owner grant typed in one session reaches the session it names

## The ruling

Owner, Cockpit item 152 (grant-plan-signoff), saved 2026-11-03 18:21 CST: pick a, "Sign off as
written". The plan `docs/plans/grant-reaches-lanes.md` then held seven questions, each with a
recommended pick. Plan section 6 holds what stands now:

- Question 1, gate the named act before the classifier: answered (a) by item 152.
- Question 2, a fixed grant word with its catalogue in code: answered (a) by item 152.
- Question 3, the first catalogue: answered (a) by item 435, 2026-11-08 11:56 CST. Gate the
  lane's `Agent` spawn first.
- Question 4, agents: moot, no pick recorded. The revalidation of 2026-11-06 found that `self-edit`
  gates nothing.
- Question 5, probe the hook gate first, the mod `tool.check` gate second: answered (a) by item 152.
- Question 6, Design A only, Design B if its probes fail: answered (a) by item 152.
- Question 7, the cloud merge rule: superseded, no pick recorded.

## The probe of a refused act

Owner, Cockpit item 435 (grant-probe-headless-arm), page answer 2026-11-08 11:56 CST, pick a:
run arm 1 headless, the 2026-11-06 way, with a refused act, and answer question 3 (a). The owner
also typed "Approved" in the lane chat at 11:55 CST. It replaces the child cloud session of item
222 (hook-allow-probe), whose settings file the guards refused. Arm 2, a sibling guard's `deny`
against the hook's `allow`, was not run.

Result, 2026-11-08 11:56-12:00 CST, Claude Code 2.1.319, nested `claude -p --permission-mode auto
--model sonnet`, hook `probe/hook_allow_probe.py` (branch `archive/hook-allow-probe`). The probed
act is a Bash write of an allow rule into `.claude/settings.local.json`, not an `Agent` spawn.

- Asked in the typed prompt, hook off: allowed, in two runs.
- Asked by a relayed file text, hook off: denied, "[Self-Modification]".
- The same, hook on: the hook emitted `allow`. The debug log then reads "Hook returned 'allow' for
  Bash, but an ask rule, a safety check, a ToolHost's person-only ask or plan mode requires the
  full permission pipeline". The classifier still denied it: "[Self-Modification]".

So, in one run, a hook `allow` did not lift a classifier refusal of a settings-file write. Which
of the four named conditions applied: unmeasured. Whether a lane's `Agent` spawn meets one of
them: unmeasured. The mod `tool.check` gate is next (question 5).

Why: the owner had to type a grant again in each session (plan, section "The problem").

Kind: build
Plan: docs/plans/grant-reaches-lanes.md#6-questions-for-the-owner (all)
