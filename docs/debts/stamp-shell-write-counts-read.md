# An unlisted shell write counts as a read

**What.** `_shell_reads` is a deny list of write forms, so an unlisted write counts as a read when its text holds a premise's Source token. Forms not listed: `python -c` or a heredoc write, `node -e`, `perl -pi`, `gh pr merge`, `git branch -D`, `curl -X POST` and `find -delete`. Mistake: a write call backs a premise it did not check. Harm: a false backing, narrowed by the token requirement.

**Where.** `hooks/precompact_handoff.py`, `_shell_reads` and its `SHELL_WRITES` list.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 15 (a handoff restamp needs evidence).

**Retire.** A red case per form above, a write call that holds a premise's token and must back nothing, passes once the write forms are refused. Test file: `hooks/test_precompact_handoff.py`.
