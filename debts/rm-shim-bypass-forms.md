# A full-path rm skips the shim

- **What.** The shim runs only when the shell finds it on PATH. `/bin/rm`, `command rm` and `find -delete` skip it.
- **Where.** `bin/rm`; the `rm-var` rule in `hooks/guard.py` reads the text of the first two.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** A guard rule refuses a recursive `/bin/rm` on a critical target, with a fixture. Or the decision records the form as accepted.
