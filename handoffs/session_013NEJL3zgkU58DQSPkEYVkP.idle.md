# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3zgkU58DQSPkEYVkP

## Reply at 2026-11-10T17:28:42Z UTC

IDLE (B). Handoff for lane cap-string-false-alarm (session_013NEJL3zgkU58DQSPkEYVkP):
- Goal: guard agent-model-cap (and the frozen-path and env-file rules) stop asking on test strings passed to an interpreter. Roadmap step agent-model-cap-string-false-alarm.
- PR #1186, branch lane/cap-string-false-alarm, head 9a5fed5d0613b64f8bacb1f9377d3d9befe8012a.
- Reviews: rounds 1 to 3 FAIL, then the owner's fix pass (item 473 a). Fix check (sonnet) PASS, net value zero. Record: PR comment 6773910281. Lane lint: PASS.
- The coordinator released it to runner 8 at 11:16 CST. It waits on merge. #1668 (session_013NEJL4AKgUjS1CWQvcdNwc) stacks on it.
- Left after merge: one docs-only notes PR (debts/notes.md). It files the debt for `python -c` / `node -e` output piped to sh, cited to decision cap-string-false-alarm; that scope also covers `> f; sh f` and `| xargs sh -c`. Its notes list the rare-form holes (perl/ruby pipe-open, pexpect/execa, `python3 x.py -c`), the scanner-test gap for _call_args, _command_spans and _js_module_names, the shell_write_hit recursion that drops predicate_command, and the re-pointed pins that cite incident time. Triage already has the _whole_script false alarm and the join-fix allow-case/mutant gap.
- Files: hooks/guard_frozen.py (shell_write_hit, py_spots, _py_import_bindings, _inline_script_at), hooks/guard_env.py (script_spots, _whole_script), hooks/guard_core.py (strip_heredoc_bodies per_body), hooks/test_guard.py.
- Nothing unpushed. Handoff file: ~/.claude/handoffs/812f9326-02e3-5225-8e3e-49f0e435aa0b.md.

