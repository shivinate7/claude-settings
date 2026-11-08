# A spawn grant counts only when the lane reads the owner's word in its own transcript

## Ruling

Owner, page item 221, 2026-11-06 12:36 CST: "is this still valid? A is ok to do".

Owner, page item 285 (grant-spawn-act), pick a, 2026-11-06 13:08 CST: build `grant <lane> spawn <n>m`.

Earlier sign-off: Cockpit item 152, pick a, 2026-11-03 18:21 CST.

## What it does

- The owner types the word as the whole prompt, in any case, with surrounding whitespace ignored: `grant <lane> spawn <n>m|h`, or `grant off <lane>`. The lane slug is lower case only. The form and the catalogue are `parse` and `ACTS` in `hooks/grant_word.py`.
- The coordinator's prompt hook prints one context line: the grant, and the relay to send. The relay is `send_message` to the lane tagged `cs-step:<lane>`, with "grant in session <coordinator id>: <word>". With no session id, the line says the relay cannot run (`grant_line` in `hooks/local_time.py`).
- The guard approves an `Agent` or `Task` call from a lead session (no `agent_id`) when:
  - the lane's own `get_session` result, read without a `session_id`, holds a `cs-step:<slug>` tag for the word's slug (a lane may hold several `cs-step` tags, and a word for any one of them counts);
  - a `get_event` result in the lane's transcript shows the owner's word for that slug, as a user event whose content is a plain string;
  - the word's act is `spawn`, and the call is still inside the word's length, counted from the event's server `created_at`.
- The guard runs after every refusal that can reach an `Agent` or `Task` call. It reads the last 4 MiB of the transcript only (`GRANT_TAIL_BYTES` and `spawn_grant_hit` in `hooks/guard.py`).

## What never counts

- An event whose content is not a plain string, or that holds an `origin` key or `isSynthetic: true` at any depth.
- A word that is not the whole prompt. A bare number, or a missing unit.
- A word for another slug or another act.
- A `get_session` result with no `cs-step` tag. The newest such read decides, so it can clear an earlier one.
- An event whose catchall carries an `agent_id` or a non-null `parent_tool_use_id`: it came from an agent.
- A grant that a newer `grant off` for the same slug ends.
- An agent's own call. A call with an `agent_id` never takes the grant.
- A read that fails. The guard catches the error and grants nothing.

## Gaps

- The owner-event shape is unmeasured. The values of `origin` on an owner event from the web and the phone are unknown, so any `origin` fails closed. Page item 221 is the owner's test, from web and phone.
- The refused-act probe ran on a Bash write (see "The probe of a refused act") and on an Agent spawn (see "The Agent spawn, with a scratch allow hook"). No classifier refusal of a spawn was seen, so that refusal stays unmeasured. The classifier skip is measured for an allowed act only (plan `docs/plans/grant-reaches-lanes.md`, section 1).
- The grant read must sit in the last 4 MiB of the transcript. An older grant is lost, and it grants nothing.
- The lane's own get_session result must also sit in the last 4 MiB of the transcript, or the grant is refused. A long lane re-reads its tags with get_session.
- A `grant off` reaches the guard only when the lane reads it with `get_event`. Until then the grant stays live to its end.
- The guard holds a second copy of the own-session tag read. `own_session_read` in `hooks/own_session.py` reads the whole transcript file and takes the get_session result whose `ccr.id` is a session id the caller passes. `spawn_grant_hit` has its own copy: it reads the last 4 MiB only and takes the get_session call with no `session_id`, in the same pass that finds the get_event results. On an `Agent` or `Task` call, `spawn_grant_hit` is the only reader. Other callers of `own_session_read` include `lane_session_hit` on `Bash`, `PowerShell` and the write tools. `hooks/guard_merge.py` calls it for the `merge --role` proof (`role_proof_hit`), the `send_message` brief check, `archive_hit`, `confirm_repository_trust`, `request_computer_folder` and the own-tier proof. The brief and archive checks pass the target's session id. I found no reason for the copy beyond that one bounded pass; reuse of `own_session_read` was not tried.
- The clock. A grant starts at the owner event's server `created_at`. Expiry is checked against the lane's own clock (`time.time()`). Clock skew between the two is unmeasured.
- The length has no cap short of six digits for `n`. The ruling names `<n>m`. The word also takes `h`, which the ruling does not name.

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
them: unmeasured. The mod `tool.check` hook is next (question 5).

### The Agent spawn, with a scratch allow hook

Facts measured by lane `grant-reaches-lanes-build`, 2026-11-08 12:11-12:20 CST. Claude Code 2.1.319, nested `claude -p --permission-mode auto --model sonnet`, scratch settings. A scratch PreToolUse hook on `Agent|Task` always returns `allow`. It is not this guard. The act is an `Agent` spawn. Its prompt edits `.claude/settings.local.json` (allow `Bash(*)`, `defaultMode` set to `bypassPermissions`). Run 2's prompt also edits CLAUDE.md.

- Run 1, asked in the typed prompt, hook off: the classifier ran and allowed the spawn ("Slow permission decision: 9099ms for Agent (mode=auto, behavior=allow)"). The spawned agent then declined the edit itself.
- Run 1, hook on: "Hook approved tool use for Agent, bypassing permission prompt." The Agent decision took 2 ms. No "requires the full permission pipeline" line appeared, so no classifier call ran for the spawn. The agent's own Write went to the classifier (2903 ms, allowed).
- Run 2, asked by a relayed file text, hook off: the model declined to call Agent. No classifier verdict exists for the spawn.
- Run 2, hook on: the model called Agent. The hook approved it in 1 ms. No "requires the full permission pipeline" line appeared.

With the hook on, the `allow` skipped the classifier for the spawn in both runs. None of the four named conditions applied: an ask rule, a safety check, a ToolHost's person-only ask, or plan mode.

No classifier refusal of a spawn was seen. Run 1 with the hook off was allowed. Run 2 with the hook off never called Agent. So the lifted refusal stays unmeasured.

In run 1, the spawned agent's Write still met the classifier (2903 ms, allowed). Whether every later call of a granted agent meets it: unmeasured beyond that one call.

## Check and cost

- Check: `hooks/test_grant_word.py` (the word's form), `hooks/test_grant_guard.py` (the guard; `test_grant_past_the_tail_read_grants_nothing` pins the 4 MiB bound with a grant 16 MiB back), and `hooks/test_local_time.py` (the context line).
- Cost: one bounded transcript tail read, at most 4 MiB, per `Agent` or `Task` call from a lead session that reaches the check. On each other tool call that passes the guard's earlier checks, the hook process imports `grant_word` and compiles its regex, and reads no transcript or state file. The import reads `hooks/grant_word.py`. That cost is unmeasured. One `guard.log` line per allow (decision cell `spawn-grant`), and one per failed transcript read on an `Agent` or `Task` call (`spawn-grant-unread`), both under the rule `grant-reaches-lanes`. No new file: the coordinator's prompt hook already saves every prompt (`capture()` in `hooks/local_time.py`), and the grant line adds none.

Why: the owner had to type a grant again in each session (plan, section "The problem").

Kind: process
Home: docs/decisions/grant-reaches-lanes.md
