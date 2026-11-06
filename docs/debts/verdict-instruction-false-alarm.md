# A reviewer brief that asks for a verdict is refused

**What.** A normal reviewer brief line, such as `End your report with a verdict: PASS, FAIL or PARTIAL.` or
`Give a verdict: PASS or FAIL`, is refused as a prior verdict. A finding that quotes `verdict: FAIL` in
backticks is refused too. The verdict-line pattern matches `verdict` anywhere before a line's first
colon, not at line start only.

**Where.** `hooks/guard.py`, `BRIEF_BLIND_VERDICT`, its first alternative `[^\n:]*?\bverdict\b`.

**Decision.** `reviewer-brief-blind`, a reviewer's brief holds no report or verdict.

**Retire.** Match the label at line start: `verdict`, or `prior`, `previous`, `last` or `earlier` before it,
and nothing else before the colon. Closed when red cases allow both brief lines above and the
`Previous round verdict: FAIL` case stays refused.
