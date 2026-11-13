# The checked-stamp rule judges only file-tool writes

**What.** The stamp rule judges only Write, Edit and MultiEdit to a session handoff, the same scope as `handoff-sections` (item 14). A bulk restamp by `sed -i` or a Python `write_text` on the handoff passes with no evidence. Mistake: Claude restamps premises through a shell write. Harm: an unbacked `Checked` line reads as checked. The writing tool in the 2026-11-09 incident is unknown, so this is unmeasured as its cause.

**Where.** `hooks/guard.py`, rule `handoff-checked-stamp`, the tool check that takes only Write, Edit and MultiEdit.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 15 (a handoff restamp needs evidence).

**Retire.** A red case, a `sed -i` on the handoff path, expects a refusal. Test file: `hooks/test_guard.py`.
