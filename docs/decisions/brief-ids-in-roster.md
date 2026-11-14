# A lane brief names a slug or a role, never a session id

## The ruling

Rule `brief-ids-in-roster` in `hooks/guard.py` refuses a lane brief that names a bare session id. Its home is `brief_roster_hit` in `hooks/guard_merge.py`, beside `brief_hit`, called right after it. The rule keeps its name: it says where the id comes from, the roster. A lane brief names a slug or a role, and the lane looks the id up in the roster.

- The incident (2026-11-13 CST): a coordinator's brief named `session_013NEJL2gw6EdrSyvHkTUEx6` for batch runner 10. The right id is `session_013NEJL2f1YCYsvLdpFqtWP3`. The id was typed by hand, not copied from the roster. A message to a wrong id wakes no one, or the wrong session. The work stalls, and the owner has to ask who does it.
- The owner ruling (2026-11-14 00:19 CST, waiting page item 819 pick b, record `own-819-b-slug-or-role` on the roadmap branch): a lane brief names a slug or a role only, never a session id. The check refuses an id in a brief, a roster id included. This settles the restart plan R22 point 3 against the roster header's "Lane briefs name these ids".
- Read: a `create_session` that tags a lane (its prompt, whatever its opener), and a `send_message` (its message) with any line that starts `Grant:` or `Lane brief:`. The line may open with markdown: `#`, `*`, `_`, `>`, `-` and spaces.
- An id: `session_`, then a digit, then letters and digits, in any case. A dot, a dash or `.md` after it is not part of it. A parameter name such as `session_id` is no id. Every bare id is refused, so a second id beside a quoted one does not clear it.
- Data, not judged: an id with a backtick or a double quote right before it and right after it. A quote elsewhere on the line hides nothing: a lone backtick, a lone double quote, an apostrophe, or a closed span with the id outside it leaves the id judged.
- The refusal tells Claude to name the slug or the role, and that the lane looks the id up in the roster. It names no file, no id and no quote mark. It gives no fetch remedy: the check reads no roster.
- The override lifts it (`owner-override`). It is not in `never_lifted`: the owner may mean the brief as it stands.
- Cost: none beyond a regex scan of the brief text. No git read, no file written, no log line beyond the refusal's own. A repo with no roster is judged the same as one with a roster.

## Known holes

- Quoted-id escape: a refused Claude can wrap the same id in backticks and pass. By design, for incident quotes. The refusal's reason does not name the escape.
- An id of another shape (no digit after `session_`) is not read.
- A brief opener on a line other than the first is read here, but `lane-one-topic` (`brief_hit`) reads line one only. Step `brief-reader-one-home` follows.
- A `send_message` to a wrong target with no id in its text passes. The target (`session_id`) is not judged.

Protected by the `brief-ids-in-roster:` cases in `tests/guard/s43200-brief-ids-in-roster.py`, red before the rule read every bare id.

Kind: process
Home: hooks/guard.py
