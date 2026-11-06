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
- The gate runs after every refusal that can reach an `Agent` or `Task` call. It reads the last 4 MiB of the transcript only (`GRANT_TAIL_BYTES` and `spawn_grant_hit` in `hooks/guard.py`).

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
- The refused-act probe has not run. The classifier skip is measured for an allowed act only (plan `docs/plans/grant-reaches-lanes.md`, section 1).
- The grant read must sit in the last 4 MiB of the transcript. An older grant is lost, and it grants nothing.
- A `grant off` reaches the gate only when the lane reads it with `get_event`. Until then the grant stays live to its end.
- The clock. A grant starts at the owner event's server `created_at`. Expiry is checked against the lane's own clock (`time.time()`). Clock skew between the two is unmeasured.
- The length has no cap short of six digits for `n`. The ruling names `<n>m`. The word also takes `h`, which the ruling does not name.

## Check and cost

- Check: `hooks/test_grant_word.py` (the word's form), `hooks/test_grant_guard.py` (the gate; `test_grant_past_the_tail_read_grants_nothing` pins the 4 MiB bound with a grant 16 MiB back), and `hooks/test_local_time.py` (the context line).
- Cost: one bounded transcript tail read, at most 4 MiB, per `Agent` or `Task` call from a lead session that reaches the check. Nothing on other tool calls. One `guard.log` line per allow (decision cell `spawn-grant`), and one per failed transcript read on an `Agent` or `Task` call (`spawn-grant-unread`), both under the rule `grant-reaches-lanes`. No new file: the coordinator's prompt hook already saves every prompt (`capture()` in `hooks/local_time.py`), and the grant line adds none.

Kind: process
Home: this record.
