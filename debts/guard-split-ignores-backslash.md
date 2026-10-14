# The guard's segment split ignores backslash escapes

- **What.** The segment split ignores backslash escapes, so `echo '; pkill foo; echo 'x'` hides `pkill`. The shell honors the escape, and `split_segments` does not. So `echo \'; pkill foo; echo 'x'` runs `pkill`, while the guard reads it as quoted text and allows it.
- **Where.** `split_segments` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `split_segments` honors a backslash outside single quotes, and `$'...'` quoting. Guard tests deny the three forms with `\'`, `\"` and `$'a\'b'`.
