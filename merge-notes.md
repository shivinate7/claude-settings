# Merge notes: lane commit-refuses-conflict-markers

## Branches and live heads (read 2026-11-09 16:35 CST)
| PR | Branch | Head | Stacks on |
|---|---|---|---|
| #2083 | cmk-git-timeout-unread | eefd0eb08747565283ee6eaa1fe8ed135546d8c4 | main |
| #2175 | cmk-unread-notes (docs-only) | c9102ee998e285c42897b39fdfcd3304ec316a80 | #2083 |
| #1937 | cmk-split-git-word | 56d3188b86418b09cf5f408bc6628352a5e60950 | main (#1593 merged) |
| #1993 | cmk-interp-body-git | a34d161b17508539fda8eb60007df45a0c41f306 | #1937 |
| #2126 | cmk-interp-notes (docs-only) | bf7f115be5e413a5607f575c8c18673250e0a302 | #1993 |

Order: merge the bottom of each stack first, then merge the moved PR below into each PR above it, then main. Use ordinary merges only: no rebase, no force. Push with `git push origin HEAD:<branch>`. One test-author owns each mixed merge whole.

## #1937 → #1993 → #2126
Check `git merge-tree` against the new main first. Keep both intents:
- #1937: `decode_ansi_c` in `segment_tokens` (hooks/guard_core.py), and the item-386 line in agents/builder.md and agents/reviewer.md.
- #1993: interpreter bodies in hooks/guard_core.py (`fold_call_operator`, `_folded_string`, `_python_runs`, `python_script_runs`, `is_python_word`, `PYTHON_VALUE_FLAGS`, `inner_commands`), and the paren depth in `_command_words` (hooks/guard_merge.py). In judge_shell (hooks/guard.py), keep main's `texts` iterable: `for segment in (part for text in texts for part in split_segments(text)):`.
- #2126: notes only. Keep both sides in docs/debts/notes.md.
Proof per code PR: `~/.claude/bin/verdict python3 hooks/test_guard.py` shows 0 FAIL.

# Per-hunk resolutions: merge origin/main into cmk-git-timeout-unread (PR #2083)

Read on main 624dcc188, from the PR head eefd0eb08. Re-check each hunk against batch 70's main before resolving.

Goal: keep main's new code and rows, and keep this PR's behaviour. A conflict-markers git read that does not start or times out counts as unread (`_GitUnread`, `CONFLICT_MARKERS_UNREAD_KIND`), and the check asks. A found triplet keeps its deny. A non-zero git exit is no hit. A bare `git add` keeps main's skip.

## hooks/test_guard.py
- One hunk: keep the PR's conflict-markers registration loop (`CMK_CHECKS`), then main's FLAG ORDER block after it. Check that the file parses and holds zero markers.

## hooks/guard_merge.py, imports (~line 13)
- Drop `git_calls` and `push_text`, which main removed.
- Keep `read_default_base_state` and `push_branch_unread`, from the PR.
- Add `push_calls`, from main.

## hooks/guard_merge.py, `conflict_markers_hit` / `_conflict_markers_hit`
- Take main's `pending` / `_repo_of` structure, inside the PR's `try` with `_held` and `_GitUnread`.
- `_repo_of` must raise `_GitUnread` when `_git` returns None (did not start, or timed out) for a folder that exists. Otherwise the PR's unread case is silently lost.
- A non-existent or None folder still skips, as on main.
- A found triplet returns its deny before any unread raise.

## docs/decisions/commit-refuses-conflict-markers.md
- Keep the PR's unread bullet.
- Cost: main's "Cost, commit:" sentence plus the PR's push text, as two bullets. The push bullet names the unpinned `git symbolic-ref` spawn from `_push_head_read`.

## Proof
- `~/.claude/bin/verdict python3 hooks/test_guard.py`: 0 FAIL.
- `~/.claude/bin/verdict python3 bin/ste-changed main`: PASS.
- Push with `git push origin HEAD:cmk-git-timeout-unread`. Ordinary merge only: no rebase, no force.

# PR #2175 (cmk-unread-notes, docs-only)
- Merge the new cmk-git-timeout-unread, then origin/main.
- If docs/debts/notes.md conflicts, keep both sides' notes. This is not expected to be a mixed merge.
- Proof: ste-changed PASS. Push with `git push origin HEAD:cmk-unread-notes`.
