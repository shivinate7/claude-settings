# A heredoc body can still end with a quote the scanner keeps open

**What.** Mistake: a script ends a quoted-delimiter heredoc body with a stray `'` and the next command is a refused one. `_split_reading` clears a quote still open at a script body's end, but two shapes slip past. (1) A quote opened by the body's last character is not cleared, an off-by-one in the span test `since < b`. Probe: `python3 - <<'EOF'` with the body `print('it\'s')` then `x = '`, then `EOF`, then `pkill -f node`: allow on this branch, deny `machine-wide-kill` on main. (2) The end-of-body clear runs only when the command holds `\'` or a backtick, so `x = 'abc` then `EOF` then `pkill -f node` is allow on main and on this branch. Harm: a later refused act reads as quoted text. The probes are code reads, not suite runs.

**Where.** `hooks/guard_core.py`: `_split_reading` (the end-of-body clear and its gate), `_script_text_spans`.

**Decision.** `agents-wait-with-monitor` (its escaped-apostrophe line); rule `building-scanner-respects-strings`.

**Retire.** Fix: change `since < b` to `since <= b`, and clear an open quote at every script body's end whatever the gate says. End state: a `tests/guard/s06591-stream.py` case for each probe expects deny, and goes red on today's code first.
