# A recovery control must not gate on the state it recovers

## The ruling

A recovery control exists for the moment its own precondition is false. Gate it on that same state, and
the gate refuses it exactly when it is needed. CLAUDE.md states the rule. Two behaviors in this repo
already follow it:

- **Rule 1b, pointer-head.** The rule refuses a command that moves HEAD off `main` in the pointer
  checkout. A move TO `main` is the recovery act, so it passes.
- **The clone is not frozen.** Rule 7 freezes `hooks`, `lint`, `agents` and `state` under the config
  directory, and the live pinned checkout `<clone>-live` and the stamped worktree
  `<clone>-live-<12 hex>` that the pin link points at now. An older stamped worktree stays writable, so
  the install can move it aside. A pin counts only when a clone sits beside it (merge-reinstalls-from-main,
  ruling 1). `cp` may copy a frozen file OUT to a path outside the frozen set, since that only reads it.
  The clone of claude-settings is a separate, unfrozen path. A hook that breaks after landing can be
  fixed at its source and reinstalled. `bash merge/install_from_main.sh` and `python3 bin/merge N --confirm`
  stay allowed, from the clone and from the pin (`hooks/guard_frozen.py`, "THE CLONE ITSELF IS NOT FROZEN").

Reason: a gate on the recovered state is silent on the day of loss. The principle comes from mailaudit,
which recorded three incidents of it. This repo has no such defect.

Kind: process
Home: rule:verification-recovery-not-gated-on-own-state
