# Banchi build steps are not claimed by the shared stamp

**What waits.** The shared stamp action (`actions/stamp`) does not claim Banchi's build steps.
A pending step is a line `` 0. `step <slug>` `` in a file directly in `docs/gates/steps/`.
Banchi numbers a step by hand today.

**Why it waits.** Banchi's own claim tool, `scripts/claim-ids.py`, reads a pending step only
from `docs/GATES.md`. That file is now a pointer. So Banchi's tool cannot claim a step in
`docs/gates/steps/`, and this engine has no working rule to copy. The owner chose to leave
steps out on 2026-09-25. See `decisions/one-shared-record-stamp.md`, "Left out, on purpose".

**What keeps it from being lost.** The engine's `--check` and `--stamp` refuse a tree that
holds a pending step marker. The refusal names this file. So on the first day Banchi writes a
pending step, the tool itself brings this item back. A marker inside a fenced code block is
refused too. A byte-order mark before a line-1 marker hides it. Both match claim-ids.py's own
grammar.

**Trigger that brings it back.** Banchi's `claim-ids.py` claims a step in
`docs/gates/steps/`. Then copy its step rules into the engine, and prove parity the same way
as for decisions.

**Owner.** The claude-settings orchestrator that takes the next Banchi stamp change.
