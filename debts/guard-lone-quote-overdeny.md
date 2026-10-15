# A lone quote in a heredoc denies a clean commit

- **What.** Commit-message rules read heredoc bodies by both readings. With an unclosed lone `'` line, a later body can be read for the wrong command. A lone quote pair, then two interpreter heredoc bodies that name a lane or record, can deny a clean commit. The cost is an over-deny: bash stops at the open quote, and a fuzz of 300k cases found no bypass.
- **Where.** The heredoc readers `heredoc_heads` and `split_segments` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** A clean commit after a lone quote pair passes, and a case in `hooks/test_guard.py` pins it.
