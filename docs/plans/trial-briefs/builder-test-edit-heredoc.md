# Brief: builder-test-edit-heredoc

The coordinator sent this brief to the real lane. The text is word for word, so it sits in a code block.

```text
Lane brief: builder-test-edit-heredoc. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U.

Read the step: `git fetch origin roadmap && git show origin/roadmap:roadmap/data/steps/builder-test-edit-heredoc.json`.
Incident (Nov 1, lane refusal-cite-reach session_013NEJL3QiaZ5zBp49opNTpu): a builder agent changed lint/test_rule_audit.py through a python heredoc in Bash before guard builder-test-edit refused its Edit tool call. The builder disclosed it and restored the file. The guard checks the Edit and Write tools only. Ask that lane by send_message for the exact command form if you need it; it is sending it as a note.
Base: origin/main 49a41651.
Task: extend guard builder-test-edit (builders never change test files; test-authors do) so a builder's shell write to a test file is refused the same way: redirection, tee, sed -i, a heredoc or an interpreter (python, node) that opens the file for write. Reuse the shell write-target scanner the guard already has for other rules (one home per capability); the test-file predicate must be the same constant the Edit path uses (rule building-allow-list-is-the-constant).
Governing: the builder-test-edit record (tci-3), roles-each-layer-proves-once, guard-guards-mistakes-only (forms Claude writes by mistake, not attacker forms), building-guard-needs-incident, building-scanner-respects-strings, verification-trust-guard-after-red, roles-review-cap-three (guard verdict change: net-value test after round 3).
Failure classes: a builder reading a test file (cat, grep, python reading it) must pass; a test-author's shell write must pass; a write to a non-test file must pass; a test-file path inside a string that is only printed must pass; a lone quote or `#` in a heredoc body does not break the scan.
Done check: test-author writes red cases first (the incident form among them) and shows them red at 49a41651; builder makes them green; lane lint green: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint` and `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`.
Models per agent-model-cap. No EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Never write the roadmap. Every owner question leaves by send_message to me in the turn you ask it (owner ruling 23:31 CST). Open a draft PR; send its number and head to batch runner 7 and to me. Report cap 20 lines, plus one Lessons line.
```
