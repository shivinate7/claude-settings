# Brief: c117, scratch deletes name an absolute quoted path

Repo: shivinate7/claude-settings, from main b031394f. One lane: builder (sonnet), then reviewer (sonnet).

## Task
A command shaped `cd "$S"; rm -rf dl/*` makes Claude Code's built-in dangerous-rm prompt fire, because it cannot follow the cd. The shape is also a real risk: if the cd fails, the rm runs in the worktree.
- The guard refuses `cd <X> ; rm -r<...> <relative target>` and `cd <X> && rm -r<...> <relative target>`, and prints the absolute form (`rm -rf "$S"/dl/*`) as the remedy. Put the check beside the rm-var family (`hooks/guard_rm_var.py`, reached through `guard.py`), and reuse `split_segments` and `segment_tokens`.
- Add one rule line to the global CLAUDE.md, in the fewest words: a delete names its target as an absolute or quoted-variable path, never after a cd. Mechanize it with the guard (outcomes-mechanize-rules) and add its row to lint/rule_mechanisms.json.
- `hooks/rm_prompt_answer.py` already allows a guarded `${NAME:?}` delete in bypass mode. Check that the absolute form the remedy prints passes it.
- Whether a permission allow rule can quiet the built-in prompt for the session's scratchpad is unknown. Do not build it; say "unmeasured, needs a local session" in the report.

## Rulings
- building-guard-needs-incident: likely risk, seen Oct 27 on the owner's screen (a scratch `cd $S; rm -rf dl/*`).
- guard-guards-mistakes-only: guard the shape Claude writes, not every shell trick.

## Failure classes
- A refusal of `cd X && rm -rf /abs/path` (absolute target: must pass).
- A refusal of `rm` with no `-r` after a cd.
- A miss when the cd and the rm sit in a subshell or after `set -e`.
- Comment openers or quotes inside the command (building-scanner-respects-strings).

## Check that proves it done
New cases in hooks/test_guard.py: red on main b031394f, green on the branch, with the Oct 27 command as the first case. Also lint/rule_audit.py, lint/hook_catalog.py --check, bin/ste-changed origin/main.

## Report
At most 15 lines: PR, head, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.
