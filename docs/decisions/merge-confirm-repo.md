# A cloud merge confirm acts only in a repo its own record names

## The ruling

Orchestrator call (lane merge-repo-dir-flag); the owner may rule otherwise. Guard rule id `merge-confirm-repo`, verdict deny. It runs beside `merge-role-proof`, after the merge-checks guard.

The mistake: a batch runner runs `merge <pr> --confirm` in a checkout that its own `cs-repo` tags do not name. The cloud allow rule for `merge * --confirm` (`merge/cloud_allow.json`) takes any arguments. Once the merge tool takes `-C PATH` / `--repo-dir PATH`, only the runner's own care keeps the merge in its own repo. The role check proves the tier, not the repo.

The harm: an unreviewed merge to another repo's main. The batch runner's grant is per build, and a build's reviews, lock and checks belong to one repo.

The incident, 2026-11-03 16:15 CST: a batch runner merged mailaudit PR #185 with `cd <mailaudit checkout> && merge 185 --confirm` from a session whose tags named claude-settings. The merge tool read the checkout from the process directory, so the `cd` was the only way to name another repo. A flag makes the same act shorter to type.

The rule:

- It judges a segment that runs the merge tool with `--confirm`, in a cloud session (`CLAUDE_CODE_REMOTE=true`). `--lane-lint` merges nothing and is not judged.
- Outside the cloud it judges `--confirm` only, never `--ready`, by the session's own role file (`session_role.local_judgement`, decision `session-tiers`). (a) An own file exists: its role must be batch-runner and its repo must equal the repo of the checkout the merge acts in. (b) No own file, or no id, and `CS_SESSION_ROLE` unset: not judged, so today's prompt stands. (c) `CS_SESSION_ROLE` set with no matching own file: refused. A local refusal gives `LOCAL_REPO_REASON`, which cites this decision.
- The checkout is the `-C` / `--repo-dir` value, read with the merge tool's own parser (`merge.build_parser`). A glued `-C`, the `=` form, the last of repeated flags and a flag after the PR number read as the tool reads them. With no flag, the checkout is the `cd X &&` directory of the command, else the working directory.
- A merge inside a subshell paren or a `bash -c`, `sh -c` or `eval` string is judged as a bare one is: the guard unwraps it (`inner_commands`) and carries the `cd` of its segment into the script. The guard follows nests to `MERGE_NEST_DEPTH` (4). Past it, a script that holds `--confirm` is refused. The bound ends the read: an unbounded nest would hit Python's recursion limit, and a crash fails open (`guard-hooks-fail-closed`). Unknown means refuse.
- The merge tool takes no flag prefix (`allow_abbrev=False`): `--conf` or `--repo` is an error, never the flag it starts, so the guard and the tool read one spelling. Main accepted prefixes; this lane refuses them.
- The repo is `git_reads.github_repo` of that checkout, the one reading the roadmap build and `lane-repo-tag` share.
- The merge passes only when a tag of the session's own newest `get_session` record names that repo (`shared_names.repo_tag_names`), and no `set_session_tags` call follows that record.
- It fails closed inside the clause: no record, an unreadable checkout, an empty flag value and flags the parser refuses are each a refusal, as in `merge-role-proof`.
- The reason names the rule and the remedy (hand the pull request to a batch runner whose `cs-repo` tags name the repo, or run `get_session` alone first). It never names the refused path or repo, so a session does not learn a retry target.

A runner that merges a second checkout runs `~/.claude/bin/merge -C <checkout> <pr> --confirm`, never `cd X && merge`, and only when its record names that checkout's repo. It runs in the foreground (Bash timeout up to 600000), never with `run_in_background`. Measured 2026-11-03 16:56 CST in a cloud auto-mode session: the foreground `merge N --confirm` matched the allow rule and ran. The same command with `run_in_background: true` went to the auto-mode classifier, which refused it. No code change follows from this.

Kind: build
Plan: docs/decisions/merge-confirm-repo.md#the-ruling (all)
Home: hooks/guard_merge.py
