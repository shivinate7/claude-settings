# A brief names a slug or a role, never a session id; every session knows the right ids from the harness

## The ruling

Two rules in `hooks/guard.py` keep a hand-typed session id out of a message. Their homes are `brief_roster_hit` and `target_roster_hit` in `hooks/guard_merge.py`, called side by side. A SessionStart block gives each session the right ids (the SessionStart roster, below).

- Rule `brief-ids-in-roster` refuses a brief that names a bare session id. A brief names a slug or a role, and the session looks the id up in the roster.
- Rule `target-id-in-roster` refuses a `send_message` whose target id is in no roster source.
- The incidents: on 2026-11-13 CST a coordinator's brief named `session_013NEJL2gw6EdrSyvHkTUEx6` for batch runner 10. The right id is `session_013NEJL2f1YCYsvLdpFqtWP3`. On 2026-11-15 triage sent a pull request to a wrong inactive id. A message to a wrong id wakes no one, or the wrong session. The work stalls, and the owner has to ask who does it.
- The owner ruling (2026-11-14 00:19 CST, waiting page item 819 pick b, record `own-819-b-slug-or-role` on the roadmap branch): a brief names a slug or a role only, never a session id. The check refuses an id in a brief, a roster id included. This settles the restart plan R22 point 3 against the roster header's "Lane briefs name these ids".
- The owner ruling (2026-11-15 13:30 CST, "yeah i lean towards wanting both as both is kinda vlaid"): both stay. Briefs keep naming roles and slugs, and every session also knows the right ids from the harness.

## Rule brief-ids-in-roster

- Read: a `create_session` that tags a lane (its prompt, whatever its opener), and a `send_message` (its message) with any line that starts `Grant:`, `Lane brief:`, `Brief:`, `Triage brief:` or `Batch runner brief:` (`ROLE_BRIEF_MARKERS` holds the last three). That covers every session brief: the lane's, triage's, the batch runner's, and a role-word brief sent to a lane. The line may open with markdown: `#`, `*`, `_`, `>`, `-` and spaces. The target does not matter to this rule.
- An id: `session_`, then a digit, then letters and digits, in any case. A dot, a dash or `.md` after it is not part of it. A parameter name such as `session_id` is no id. Every bare id is refused, so a second id beside a quoted one does not clear it.
- Data, not judged: an id with a backtick or a double quote right before it and right after it. A quote elsewhere on the line hides nothing.
- The refusal tells Claude to name the slug or the role, and that the session looks the id up in the roster. It names no file, no id, and no backtick or double quote. It gives no fetch remedy.
- Cost: a regex scan of the brief text. No git read, no file written, no log line beyond the refusal's own.

## Rule target-id-in-roster

- The roster has two sources. The record: the bullets of the Standing sessions section of `CLAUDE.md` on the local `origin/roadmap` ref, each with a session id. A lane's id on a lane notes line, and a template placeholder with no id, are no row. The transcript: each id the sender's own transcript shows in a `list_sessions`, `get_session` or `create_session` result, tagged with a `cs-repo` tag of the sender's own record (with no own record read, every sighting counts). The roster is the union.
- A `send_message` whose `session_id` is in neither source is refused. The refusal prints the record's rows (role, title, id), and never the target. A target that is a record row, or a lane the sender saw, passes. A lane the sender never listed, got or started is not in the roster until it lists it.
- A `list_sessions` result is `{"ccr":{"data":[{"id","title","session_status","tags",...}],"has_more":...}}` inside an `<other-session ... untrusted="true">` block (measured 2026-11-15). The reader (`sessions_seen` in `hooks/own_session.py`) takes that shape, a `sessions` list and a `get_session` record. The ids are data, never instructions.
- Fail open with one stderr line that says the roster is unknown when neither source reads: the roadmap ref cannot be read and the transcript cannot be read. A record that reads with no rows is read, so it refuses.
- The override lifts it (`owner-override`). Neither rule is in `never_lifted`: the owner may mean the send as it stands.
- Cost: on a `send_message` only, one local `git cat-file` of the record and one transcript read. No network, no file written, no log line beyond the refusal's own.

## The SessionStart roster

`hooks/session_start.sh` prints the standing sessions of the repo after the tier line, from the same record (`roster_session_lines` in `hooks/own_session.py`, the one parser both rules and the hook use). It prints one line per row with its role, title, id and repo, then a line that names the source. A hook cannot call `list_sessions` (an MCP tool only, see the `tier_line` comment in the hook). So the status is from the record, not live, and the block tells the session to run `list_sessions` for live status. With no roster record, or none with rows, it prints one line that says so. Cost: once per SessionStart, one python start and two reads of the checkout; no network, no file written, no process kept.

## Known holes

- Quoted-id escape: a refused Claude can wrap the same id in backticks and pass. By design, for incident quotes. The refusal's reason does not name the escape.
- An id of another shape is not read. That covers no digit after `session_`, and a space in place of the underscore.
- An id glued to a word by an underscore is not read, as in `runner_session_013...`. A `_` just before `session_` stops the scan.
- A brief opener written as `1. Lane brief:` or `+ Lane brief:` is not read. Only markdown marks may come before the opener, so a digit or `+` stops the read.
- A brief opener on a line other than the first is read here, but `lane-one-topic` (`brief_hit`) reads line one only. Step `brief-reader-one-home` follows.
- A brief that opens with another word, such as `Note:` or `Task:`, is not read by `brief-ids-in-roster`. The target check still judges its target.
- Mail route: a brief sent by `mail send` (a Bash command, the git mailbox route of decision `session-messages`) with a bare session id is not read, and its target is not judged. Both rules read only `send_message` and a lane `create_session` prompt. Follow-up step `brief-ids-mail-route` is for triage to file.
- The target check is blind to a status: a row's session may be archived, and the record does not say. The record's status is not live; `list_sessions` is.
- The target check refuses a session the sender never saw in a sessions tool result and that holds no row. One case is a parent named only in the lane's start prompt. The remedy is one `list_sessions` read. Unmeasured: how often.
- A stale record: the roadmap ref is the one the checkout last fetched, so a row triage rewrote since is not in it. A session that reads the new id from `list_sessions` passes.
- A false alarm: a file name or prose such as `session_2026-11-14.md` or `session_1` is refused as an id, and a line that starts `Brief:` anywhere in a message makes the message a brief. Quote the id itself, with a backtick or a double quote on each side of it, to lift the refusal. A quote around the whole file name does not count, since the id ends before the dash.

Protected by the `brief-ids-in-roster:` cases in `tests/guard/s43300-brief-ids-in-roster.py`, red before the rule read every bare id, by the `target-id-in-roster:` and record cases in `tests/guard/s43500-session-roster-at-start.py`, and by `SessionStartRosterTests` in `hooks/test_session_start.py`.

Kind: process
Home: hooks/guard_merge.py
