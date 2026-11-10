# The checked-stamp rule refuses some read-only shell calls

**What.** The stamp rule counts three read-only shell calls as no evidence. A nonzero exit counts as failed, so a `grep` that finds nothing backs nothing. `GIT_WRITES` lists `stash`, `tag` and `config`, so `git stash list`, `git tag -l` and `git config --get` back nothing. A heredoc `>` in its body reads as a redirect. Mistake: Claude runs a read-only check and the rule refuses its restamp. Harm: one retry each. The escape is another successful read, `Checked never`, or an owner override. No dead end.

**Where.** `hooks/precompact_handoff.py`, `backed_premises` (its `failed_tool_use_ids` call), `_shell_reads` and `GIT_WRITES`.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 15 (a handoff restamp needs evidence).

**Retire.** A case per form above, each a read-only shell call that must back its premise, fails on the old code and passes on the fix. Test file: `hooks/test_precompact_handoff.py`.
