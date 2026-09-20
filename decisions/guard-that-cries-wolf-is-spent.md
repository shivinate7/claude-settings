# A guard that cries wolf is spent

CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards."
This entry records the missing half, and the two false alarms that made the
half worth writing down. A guard that goes red when nothing is wrong is
spent. The reader learns to scroll past it.

## The shared shape

Both false alarms below matched text instead of resolving the act. Neither
looked at what a command would actually run. Each treated the presence of a
substring as proof of an act. That argument, and why it fails, is recorded
already. See decisions/predicate-is-the-act.md. This entry does not restate
it. It adds two more measurements of the same shape, from a different file.

## False alarm 1: session_start.sh warns in every repo that is not the pointer clone

`hooks/session_start.sh` compared the pointer target `CLAUDE.md` against the
current checkout's `CLAUDE.md` whenever both files existed. It never checked
whether the current checkout was a clone of the same repository the pointer
names. In any other repo, the two files differ by design. The line printed
every session, everywhere.

Reproduction, before the fix:

```
printf '{"cwd":"/Users/shivinate/Developer/pkmnscan"}' | sh hooks/session_start.sh
```

This printed a divergence line for `pkmnscan`, a repository with its own
`CLAUDE.md` and no relation to claude-settings. The check read the file
content. It never read the identity of the tree that held it.

## False alarm 2: report_gate.py accused a turn that landed nothing

`lint/report_gate.py` ran a regex over the raw text of every Bash command in a
turn. It searched for `git commit`, `git push`, or `git merge`. It never
parsed the command. A read-only Bash call in this session held the quoted
probe list `'git commit -q -m x' 'git push --quiet'`, written to test a
fixture. The words sat inside single quotes. They never ran. The gate still
demanded the closing report, for a turn that landed nothing.

Fixture pinning this, in `lint/test_gates.py`:

- `test_58_quoted_git_commit_in_probe_list_passes`
- `test_59_heredoc_body_naming_git_merge_passes`

Both fail against the pre-fix `report_gate.py`. Both pass against the fix,
which imports `guard.py`'s tokenizer instead of reading raw text.

## What this changes

Extend the CLAUDE.md sentence. Trust a guard only once it goes red on its own
defect. A guard that goes red on nothing is spent, because the reader stops
reading it.

A predicate that matches text is not a predicate on the act. Resolve the act
instead. `hooks/guard.py` already does this, with `split_segments`,
`strip_heredoc_bodies`, and `resolve_command`. Or gate on identity before
content, the way the fixed `session_start.sh` now compares
`git remote get-url origin` in both trees, before it reads either file.
