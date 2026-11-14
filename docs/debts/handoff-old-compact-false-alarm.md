# Old compactions open the Stop gate

**What.** With no `compact` record in the session's `<session>.nudge.json`, the gate treats the newest `compact_boundary` in the transcript as a new compaction. A session that compacted before the gate deployed is refused up to 3 times at its first Stop, one Sonnet agent asked each time. A forked or resumed transcript that carries an old boundary may be refused the same way (unmeasured). The fix idea seeds `compact` as done when the state holds a bucket but no compact record. A session with no state at all is not covered by that seed.

**Where.** `hooks/precompact_handoff.py`, function `_gate`. With no `compact` record, `comp_open` is true for any boundary.

**Decision.** `precompact-handoff`, checkpoints keep the handoff current (item 4, the Sonnet subagent gate).

**Retire.** An old boundary with no `compact` record opens nothing, in a session with a bucket in its state and in one with no state. `hooks/test_precompact_handoff.py` holds a case for each: the first Stop passes with no refusal. Both cases go red on the current code. A new boundary written after the seed still refuses.
