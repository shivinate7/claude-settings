# Brief: env-heredoc-false-alarm

The coordinator sent this brief to the real lane. The text is word for word, so it sits in a code block.

```text
Lane brief: env-heredoc-false-alarm. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U.

Read the step: `git fetch origin roadmap && git show origin/roadmap:roadmap/data/steps/env-heredoc-false-alarm.json`.
Incidents: (1) Nov 1 23:41 CST, main's env-file guard refused triage 5's Bash command that only wrote a roadmap JSON note, because the note's text named an env folder inside a python heredoc string. (2) Nov 1 23:38 CST, the same guard refused the coordinator's `cat > <scratchpad>/brief.md <<'EOF' ... EOF` that wrote this brief, because the brief text named env-file forms. No env file was read or written either time.
Base: branch lane/env-file-scope at 9743a815 (PR #1057, draft, stacked on #1046). It rewrote the env predicate (names_env_file). Branch from it; your PR stacks on #1057 and merges after it.
Task: 1) Turn note env-file-rule-false-alarms (docs/debts/notes.md) into a debt record in docs/debts, citing both incidents and decision env-file-stays-unread. 2) Change the guard's verdict so env-file words inside a heredoc body that only writes a file (no read of an env file, no command that runs the body against one) pass. Find the refusal (env_heredoc_refusal) and its scanner; reuse the shell tokenizer the guard already has (rule building-scanner-respects-strings).
Governing: env-file-stays-unread, guard-guards-mistakes-only, building-guard-needs-incident (a guard or check needs a mistake Claude has made or is likely to make in normal work), verification-trust-guard-after-red, roles-review-cap-three (guard verdict change: net-value test after round 3).
Failure classes: a heredoc piped into a shell or interpreter that then reads an env file must still refuse; a plain read of an env file outside a heredoc still refuses; a heredoc whose body is data written by `cat > file <<EOF` passes; a lone quote or `#` inside the body does not break the scan.
Done check: test-author writes red cases first (both incident commands' forms among them) and shows them red at 9743a815; builder makes them green; lane lint green: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint` and `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`.
Models per agent-model-cap. No EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Never write the roadmap. Every owner question leaves by send_message to me in the turn you ask it (owner ruling 23:31 CST). Open a draft PR based on lane/env-file-scope; send its number and head to batch runner 7 (note: after #1057) and to me. Report cap 20 lines, plus one Lessons line.
```
