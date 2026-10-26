# The installer refuses a linked worktree, except the live pin

## The ruling

The installer refuses a linked worktree. The one exception is exactly `<clone>-live`, detached at the clone's local main commit (owner ruling 2026-10-15).

- The path alone is not enough. A `-live` worktree on a lane branch, or detached at another commit, is refused.
- `install.sh` and `install.ps1` refuse before any write. A refusal exits non-zero, leaves the config pointer and the config folder as they were, and writes nothing into `HOME`.
- Session start prints no off-main line for the pin at main's commit (owner ruling 2026-10-15). A pin at any other commit gets one off-main line that names the pin.

Reason: a linked worktree is often a temporary checkout, and an install from it would point the global config at that checkout. The pin is the one linked worktree that stays at main (`merge-reinstalls-from-main`, each merge reinstalls from the main checkout).

Kind: build
Plan: docs/decisions/install-refuses-linked-tree.md#the-ruling (all)
Home: install.sh
Home: install.ps1
Home: hooks/session_start.sh
