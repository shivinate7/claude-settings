# A lane brief names only roster ids

## The ruling

Rule `brief-ids-in-roster` in `hooks/guard.py` refuses a lane brief that names a bare session id the roster does not hold. Its home is `brief_roster_hit` in `hooks/guard_merge.py`, beside `brief_hit`, called right after it. Layer: the lane `brief-ids-from-roster`, 2026-11-13 CST, after the incident below.

- The mistake (2026-11-13 CST): a coordinator's brief named `session_013NEJL2gw6EdrSyvHkTUEx6` for batch runner 10. The right id is `session_013NEJL2f1YCYsvLdpFqtWP3`. The id was typed by hand, not copied from the roster.
- The harm: a message to a wrong id wakes no one, or the wrong session. The work stalls, and the owner has to ask who does it.
- Read: a `create_session` that tags a lane (its prompt, whatever its opener), and a `send_message` (its message) with any line that starts `Grant:` or `Lane brief:`. The line may open with markdown: `#`, `*`, `_`, `>`, `-` and spaces.
- The roster: the ids in the `## Standing sessions` list of the roadmap branch's top-level notes file, read from `refs/remotes/origin/roadmap` (`override.STEP_REF`) of the payload's repo. The section starts at a heading line that begins `## Standing sessions`, with any suffix, and ends at the next `## ` heading. A `###` line stays inside it. An id elsewhere in that file is not on the roster.
- An id: `session_`, then a digit, then letters and digits, in any case. A dot, a dash or `.md` after it is not part of it. Ids compare without case. A parameter name such as `session_id` is no id. Every bare id is judged, so a roster id beside a wrong one does not clear it.
- Data, not judged: an id with a backtick or a double quote right before it and right after it. A quote elsewhere on the line hides nothing: a lone backtick, a lone double quote, an apostrophe, or a closed span with the id outside it leaves the id judged.
- The refusal's remedy is `git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap`, then copy the id from the roster. It names the roster, not the file, and never the wrong id.
- Fails open: no roadmap ref, no Standing sessions section, a roster with no id in it, an unreadable ref, or an error in the read. Child repos have no roster, so a closed check would refuse every lane brief there.
- The override lifts it (`owner-override`). It is not in `never_lifted`: the owner may mean the brief as it stands.
- Cost: one `git show` per lane brief read. No file written, no log line beyond the refusal's own.

## Known holes

- Fail open with no roster (above). A repo that never fetched the roadmap branch is unchecked.
- A `send_message` to a wrong target with no id in its text passes. The target (`session_id`) is not judged: lanes are not on the roster, so a roster check on it would refuse every lane brief.
- A lane's id is not on the roster, so a bare lane id in a brief is refused. The escape is a quote on both sides of the id.
- Quoted-id escape: a refused Claude can wrap the same wrong id in backticks and pass. By design, for incident quotes. The refusal's reason does not name the escape.
- The roster read empties, and the check fails open, when the roster heading does not begin `## Standing sessions`.
- Two readers disagree on a lane brief opener. This check reads a `Lane brief:` line on any line of the message. `lane-one-topic` (`brief_hit`) reads line one only. Owner pick pending. Recommendation: read any line in both.
- The roster is read from the local copy of the ref. A stale copy refuses an id added since the last fetch (the remedy's fetch fixes it) and passes an id since removed.
- An id of another shape (no digit after `session_`) is not read.

## Conflict for the owner

Two records disagree. This check settles neither. It enforces only that an id a brief names is a roster id.

- Restart plan R22 point 3: "A page item, brief or handoff names a lane slug or role, never a session id."
- The roster header on the roadmap branch: "Lane briefs name these ids."

If R22 point 3 stands, the better rule refuses any bare id in a brief, and the wake path reads the id from the roster at send time. If the roster header stands, this rule is the whole check.

Protected by the `brief-ids-in-roster:` cases in `tests/guard/s43200-brief-ids-in-roster.py` (24 deny, 22 allow, 46 in all), red before the rule landed.

Kind: process
Home: hooks/guard.py
