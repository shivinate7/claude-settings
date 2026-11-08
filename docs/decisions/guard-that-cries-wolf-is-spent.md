# A guard that cries wolf is spent

## The ruling

CLAUDE.md: "Trust a guard only once it goes red on the defect it guards." The other half: a guard that goes red when nothing is wrong is spent, because the reader stops reading it.

- A predicate that matches text is not a predicate on the act (`predicate-is-the-act`). Resolve the act instead. `hooks/guard.py` already does this with `split_segments`, `strip_heredoc_bodies` and `git_calls`. Import the resolver, do not re-derive a part of it.
- Or check identity before content. `hooks/session_start.sh` compares `git remote get-url origin` in both trees before it reads either `CLAUDE.md`, so it warns only in a clone of the repository the pointer names.
- `lint/report_guard.py` imports the guard's tokenizer and `git_calls`, which walks past `sudo` and every value-taking option, `-C` included, to the real subcommand. So `git -C /path commit` counts as a landing, and a quoted `git commit` in a probe list or heredoc body does not. `lint/test_report_guard.py` pins both: `test_58_quoted_git_commit_in_probe_list_passes` and `test_59_heredoc_body_naming_git_merge_passes`.
- The same module counts `git revert` and `git cherry-pick` as landings, unless the call carries `--abort`, `--quit`, `-n`, `--no-commit`, `-h` or `--help`. It counts `gh pr merge`, `gh pr create` and `gh pr update-branch`, unless `--help` or `-h`, `--disable-auto` on merge, or `--web` or `-w` on create. It counts `delete_file`, `update_pull_request_branch` and `enable_pr_auto_merge` among the landing GitHub tools. The gh call is read through the merge guard's `gh_call_of`, never a pattern over the command text. `lint/test_report_guard_landing.py` pins each call and its controls. A landing counts from the last human message, or from a later peer message when the last user or assistant record before it is a reply with no tool call; a peer message after a tool result keeps the earlier landing.
- Owner, 2026-11-01 04:26 CST (waiting-page item 110, pick a): before you route around a refusal, read the guard's record. If the record seems to allow the act, your report flags a possible false alarm. Incident: 2026-10-31, three sessions routed around the builder-test refusal without asking.

The guard's worktree-remove rulings are in `agent-worktree-discard-is-noted` (a discard or remove in a worktree).

Kind: process
Home: rule:verification-cry-wolf-guard-is-spent
