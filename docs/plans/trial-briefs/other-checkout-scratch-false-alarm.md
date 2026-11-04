# Brief: other-checkout-scratch-false-alarm

The coordinator sent this brief to the real lane. The text is word for word, so it sits in a code block.

```text
Lane brief: other-checkout-scratch-false-alarm. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U.

Read the step: `git fetch origin roadmap && git show origin/roadmap:roadmap/data/steps/other-checkout-scratch-false-alarm.json`.
Incidents: the other-checkout guard refused writes in a session's own scratchpad worktree after a cd, though its record exempts that path. (1) Lane cc-update-behavior-diff, Nov 1 22:00 CST, after a resume. (2) The coordinator, Nov 1 23:28 CST: `cd <scratchpad>/wt-notes && git add ... && git commit ...` refused with "this write lands in another checkout of this clone"; the same commit with `git -C <scratchpad>/wt-notes` passed. (3) Triage 5, Nov 1: a cd into its roadmap worktree plus a heredoc.
Base: origin/main 49a41651.
Task: change the guard's verdict so a write in the session's own scratchpad worktree (the path its record exempts) passes after a cd, as it does with git -C. Find the other-checkout rule in hooks/guard.py (or its module) and the exemption its record names; fix the cause (why the cd form misses the exemption), not one form.
Governing: the other-checkout rule's record, shared-trees-one-checkout-per-agent, guard-guards-mistakes-only, building-guard-needs-incident (three named incidents, date them), verification-trust-guard-after-red, roles-review-cap-three (guard verdict change: net-value test after round 3; the reviewer checks no other checkout opens).
Failure classes: a cd into ANOTHER session's worktree or the main checkout must still refuse; a cd chain that ends outside the scratchpad must still refuse; a scratchpad path reached through a symlink or `..` is judged by its real path; a resumed session (new cwd) still matches its own scratchpad.
Done check: test-author writes red cases first (incident 2's exact form among them) and shows them red at 49a41651; builder makes them green; lane lint green: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint` and `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`.
Models per agent-model-cap. No EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Never write the roadmap. Every owner question leaves by send_message to me in the turn you ask it (owner ruling 23:31 CST). Open a draft PR; send its number and head to batch runner 7 and to me. Report cap 20 lines, plus one Lessons line.
```
