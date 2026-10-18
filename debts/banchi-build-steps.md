# The shared stamp does not claim Banchi build steps

**What.** A pending Banchi step is a line `` 0. `step <slug>` `` in a file in `docs/gates/steps/`. Banchi numbers it by hand. Banchi's `claim-ids.py` reads a pending step only from `docs/GATES.md`, now a pointer, so no working rule exists to copy. Until Banchi's config carries an `unclaimed` entry for a step marker, a pending step passes in silence.

**Where.** `actions/stamp`, and Banchi's stamp config.

**Decision.** `one-shared-record-stamp`, one shared parser, not four claim tools.

**Retire.** Revisit when `claim-ids.py` claims a step in `docs/gates/steps/`. Then copy its rules into the engine and prove parity as for decisions. Closed when the stamp claims a step.

## Ruling

Owner, 2026-09-25: Banchi build steps stay out of the stamp.
