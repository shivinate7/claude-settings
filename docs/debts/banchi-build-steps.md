# The shared stamp does not claim Banchi build steps

**What.** A pending Banchi step is a line `` 0. `step <slug>` `` in a file in `docs/gates/steps/`. Banchi numbers it by hand. Banchi's `.github/stamp.json` carries an `unclaimed` entry for the step marker, so the stamp refuses a pending step and never numbers it.

**Where.** `actions/stamp`, and Banchi's stamp config.

**Decision.** `one-shared-record-stamp`, one shared parser, not four claim tools.

**Retire.** Revisit when the owner moves a step into the stamp. Then copy its rules into the engine and prove parity as for decisions. Closed when the stamp claims a step.

## Ruling

Owner, 2026-09-25: Banchi build steps stay out of the stamp.
