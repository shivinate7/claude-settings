# The guard's segment split ignores backslash escapes

- **What.** The split now honors every backslash escape outside single quotes, and `$'...'`. A guard test denies the `$'a\'b'` form. No guard test denies the `\'` and `\"` forms, such as `echo \'; pkill foo; echo 'x'`, so a regression there would go unseen.
- **Where.** `quote_advance` and `split_segments` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `split_segments` honors a backslash outside single quotes, and `$'...'` quoting. Guard tests deny the three forms with `\'`, `\"` and `$'a\'b'`.
