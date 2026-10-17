# An expanded glob passes the rm shim

- **What.** The shell expands `*` before the shim runs, so `rm -rf *` in the cwd arrives as a list of children and passes. The cwd itself is not an operand.
- **Where.** `bin/rm`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** The shim refuses a recursive call whose operands are every child of the cwd or of home, with a fixture. Or the decision records the form as accepted.
