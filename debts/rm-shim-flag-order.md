# The rm shim reads a flag after an operand as a flag

- **What.** On macOS `rm dir -rf` treats `-rf` as a file name. The shim reads it as a flag, so it may refuse a call that BSD `rm` would not run as recursive. One retry fixes it.
- **What, abbreviations.** GNU `rm` reads `--rec` and `--recur` as `--recursive`. The shim does not read them as recursive, so such a call is not judged.
- **Where.** The argument loop in `bin/rm`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** The shim reads flags the way the host `rm` does, with a fixture on macOS and Linux. Or the decision records the false alarm and the missed abbreviations as accepted.
