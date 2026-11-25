# A spawn refusal carries the judge's reason

**What.** A refusal of a spawn by the judge (rule `spawn-judge`, an `Agent` call) carries the judge's reason as written, then `SPAWN_CITE`.

**Where.** `main` in `hooks/call_judge.py`: an `Agent` call has no units, so `cite` is empty, `past` is False, and `refuse` gets the verdict's `reason`, or the entry's fallback when it is blank.

**Harm.** A session may read a judge's order as an instruction.

**Decision.** `guard-remedy-not-to-owner` (the refusal remedy text; it does not name the spawn path).

**Retire.** Retired when a spawn refusal's text is code-written, or shows the judge's reason as quoted data. Test: `hooks/test_call_judge.py`.
