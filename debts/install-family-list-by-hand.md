# The guard module list is kept by hand

- **What.** The guard's module list `_FAMILY_MODULES` is kept by hand. A new guard module left off it is not compared.
- **Where.** `_FAMILY_MODULES` in the guard, `hooks/guard.py`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** A check compares `_FAMILY_MODULES` with the guard files on disk, and goes red on a missing entry.
