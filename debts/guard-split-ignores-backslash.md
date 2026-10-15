# The guard's segment split ignores backslash escapes

- **What.** The split now honors `\'`, `\"`, `\\` and `$'...'`, but no guard test pins this for the kill rule. A regression could let `echo \'; pkill foo; echo 'x'` hide `pkill` again, and no case would go red.
- **Where.** `quote_advance` and `split_segments` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `split_segments` honors a backslash outside single quotes, and `$'...'` quoting. Guard tests deny the three forms with `\'`, `\"` and `$'a\'b'`.
