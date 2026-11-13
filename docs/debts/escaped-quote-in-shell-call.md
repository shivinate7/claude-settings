# A loop inside an interpreter's own shell call reads as allow when the string holds an escaped quote

**What.** Mistake: a script runs a wait loop through its own shell call, in a string with `\'`. Probes: `os.system('echo it\'s; while true; do sleep 3; done')`, perl `system('echo it\'s; ...')` and node ``execSync(`while true; do sleep 3; done`)`` are allow on this branch and deny `waiter` on main. Main refused them by parity luck: the same loop without the escape is already allow on main. Harm: a wasted-turn loop, low. The probes are code reads, not suite runs.

**Where.** `hooks/guard_core.py`: `_split_reading`, `_script_text_spans`.

**Decision.** `agents-wait-with-monitor` (agents wait with Monitor).

**Retire.** Fix: read a string handed to a shell call inside a script body as shell text. End state: a `tests/guard/s06591-stream.py` case runs each probe and expects deny `waiter`, red on today's code first.
