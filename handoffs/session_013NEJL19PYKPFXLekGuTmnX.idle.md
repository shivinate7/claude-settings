# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL19PYKPFXLekGuTmnX

## Reply at 2026-11-10T17:26:02Z UTC

IDLE (B). Handoff for lane merge-repo-dir-flag (session_013NEJL19PYKPFXLekGuTmnX):
- Goal: the merge tool's `-C`/`--repo-dir` flag and the merge-confirm-repo guard (#1166), plus two follow-ups: #2504 (replaces #1982, a reason ending `)`/`&` no longer hides `-C`) and #2509 (replaces #2106, a quoted `)` or `|`/`;`/`&&` inside `$( )` no longer hides `-C`/`--confirm`).
- State: all three released to coordinator session_013NEJL2hB1pLZPDpzas7VgB at 09:23 CST. Each has its review record posted verbatim and lane lint PASS. Merge order:
  - #1166: head 6076b2b52, record 6769830005;
  - #2504: head df5d9d11d, record 6769467975;
  - #2509: head ef07fd89e, record 6769632867.
- Left, after the stack merges: one docs PR with these notes in docs/debts/notes.md:
  - escaped `\$(` inside `bash -c`;
  - ANSI-C `$'…'` before `-C`;
  - `echo it's && merge --confirm` is denied in the session's own checkout;
  - `--head "$HEAD"` is denied with the repo reason;
  - the literal remedy also covers a flag value;
  - `X=$(a|b) merge` and `<(…)` are allowed;
  - a backtick holding a pipe is allowed;
  - the open-`$(` `--confirm` arms have no mutant, and the `_glued_counts` raise arms have no test;
  - `out=$(merge …)`;
  - `hit_suites` reverts a claim on an unreadable workflow folder.
  Also: remove the duplicate note merge-inside-subst-unjudged (merge-in-substitution-after-cd covers it); add the literal reason to decision merge-confirm-repo; a test-author fixes the hooks/test_guard.py comment near the `$(` cases and adds a case that a cut-open `$(` without `--confirm` is allowed.
- Steps queued with the coordinator: note-cause-cites-code, ste-on-object-commits, note-slug-dup-check.
- Files: hooks/guard_merge.py, hooks/guard.py step 6a1, hooks/test_guard.py section 5h, hooks/mutate_guard.py, merge/merge.py, docs/debts/notes.md. Handoff file: /root/.claude/handoffs/a467bbee-46cc-529f-b2d3-a189144e5f04.md.

