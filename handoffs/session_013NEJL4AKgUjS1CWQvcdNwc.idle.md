# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL4AKgUjS1CWQvcdNwc

## Reply at 2026-11-10T17:28:42Z UTC

IDLE (B). Lane notes-fix-reverify-large, session_013NEJL4AKgUjS1CWQvcdNwc, repo shivinate7/claude-settings, parent coordinator session_013NEJL2hB1pLZPDpzas7VgB.
Goal: fix the 5 large notes rows, one PR per row, and hand each reviewed PR on (coordinator brief, 2026-11-07 14:23 CST).
Merged already: #1494, #1506, #1667, #2247.
#1597 claude/mutant-crash-audit, head 2d29d2eced423bf6eeea6e341f3441061b90568f: reviewed (record comment 6761728852, Sonnet round 3 PASS, net positive), lane lint PASS. It is in batch 72 (#2551, batch-72i). Left: nothing unless batch 72 goes red; then merge main, run the silent-undo check, review, record, lint, and hand to the coordinator.
#2508 claude/heredoc-quote-restore, head 6201185f2f40de754c68511b59a4c5f0d09bd184: reviewed (record comment 6763297147, round 3 PASS, net positive), lane lint PASS, NOT released (coordinator 11:17 CST).
Left on #2508: after #1186 (9a5fed5d0) lands, merge main. A test-author must resolve the conflict in hooks/mutate_guard.py (test config). Then a Sonnet fix check (none used on this chain yet), the record, lane lint, and the head to the coordinator. guard_core.py carries the same spans kwarg as #1186 and merges cleanly.
Left, docs-only notes PR to docs/debts/notes.md after both land:
- a one-case control misses a partial layout fault;
- a fragment that matches only a SKIP row reads its whole target UNKNOWN, and no test pins this;
- a missing guard.py hangs test_guard.py until 1200 s;
- one flaky control turns all of its target's mutants UNKNOWN;
- $( ), backtick and <( ) after a lone-quote body stay hidden, because guard_env _substitutions walks uncut text;
- the `if not quote:` cut arm (~guard_core.py:286) survives an `if False:` mutant and may be equivalent.
Re-check the LEAK_FORMS <<- and two-heredoc cases first, and check for duplicate slugs after the merge=union merge.
Archive: archive/heredoc-quote-leak-1186-2609db784 (c6555629d). Full handoff: /root/.claude/handoffs/f32bfcd0-1a36-5f5a-9c5d-82086e70fded.md. I am deleting my pending check-in, trig_013kgL316JnQndM6yQwvjKA8.

