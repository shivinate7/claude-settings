# Banchi build steps are not claimed by the shared stamp

**What waits.** The shared stamp action (`actions/stamp`) does not claim Banchi's build steps.
A pending step is a line `` 0. `step <slug>` `` in a file directly in `docs/gates/steps/`.
Banchi numbers a step by hand today.

**Why it waits.** Banchi's own claim tool, `scripts/claim-ids.py`, reads a pending step only
from `docs/GATES.md`. That file is now a pointer. So Banchi's tool cannot claim a step in
`docs/gates/steps/`, and this engine has no working rule to copy. The owner chose to leave
steps out on 2026-09-25. See `decisions/one-shared-record-stamp.md`, "Left out, on purpose".

**What keeps it from being lost.** The engine's `--check` and `--claim` can refuse a tree
that holds a pending step marker. The repo's own config must have an `unclaimed` entry for it.
Since 2026-09-28 the parent names no repo (`record-stamp-stays-generic`). So Banchi's own
config must carry that entry, with a message that names this file. No adoption brief
carries that step yet. Until Banchi's config has the entry, a pending step passes in
silence. With the entry, the tool itself brings this item back on the first day Banchi writes a
pending step. The `pattern` in Banchi's own entry now decides two cases. One is a marker in a fenced
code block. The other is a marker after a byte-order mark.

**Trigger that brings it back.** Banchi's `claim-ids.py` claims a step in
`docs/gates/steps/`. Then copy its step rules into the engine, and prove parity the same way
as for decisions.

**Owner.** The claude-settings orchestrator that takes the next Banchi stamp change.
