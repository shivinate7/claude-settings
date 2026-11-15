# Brief: red-main-stale-schedule

The coordinator sent this brief to the real lane. The text is word for word, so it sits in a code block.

```text
Lane brief: red-main-stale-schedule. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U.

Incident (Nov 2 00:01 CST, batch runner 8 on joyous #68): the merge tool's red-main check refused because of joyous links run 40323547948, a schedule run from Oct 26 on old main eb7800528 (job readme-links red). A newer dispatch run of the same workflow file on current main 53b50465e, run 41397308885, passed. Under decision no-merge-onto-red-main (as changed by #1013, ci-alarm-reads-by-event), `schedule` is its own event group, so no dispatch or push run can clear a schedule red; the stale red blocks every joyous merge until the next scheduled links run. #1013's reason (coordinator brief, Nov 1 19:44 CST): a green nightly must not clear a red push, because the two events can run different job sets.
Base: origin/main 49a41651.
Task: keep #1013's protection and drop the false block. A newer completed run of the same workflow file on the base clears an older red run of another event group only when it ran every job the red run had (same job names) and those jobs passed. Otherwise the groups stay separate as today. Change the one home that judges runs (merge/merge.py judge path and actions/ci-alarm/events.json reader; the CI alarm reads the same file, so keep one rule for both or say why not). Rewrite decision no-merge-onto-red-main in place to state the rule; cite this incident with its date.
Governing: no-merge-onto-red-main, ci-alarm-reads-by-event, building-one-home-per-capability, building-guard-needs-incident, verification-trust-guard-after-red, roles-review-cap-three (a check verdict change: net-value test after round 3; the reviewer checks no red that main refuses now passes).
Failure classes: a green nightly whose job set differs from the push run must still not clear a red push; a cancelled newer run stays UNKNOWN and clears nothing; a newer run still in progress waits; a red newer run stays red; job names compared exactly, not by prefix.
Done check: test-author writes red cases first (the joyous form: old schedule red, newer dispatch green with the same jobs) and shows them red at 49a41651; builder makes them green; lane lint green: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint` and `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`.
Models per agent-model-cap. No EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Never write the roadmap. Every owner question leaves by send_message to me in the turn you ask it (owner ruling 23:31 CST). Open a draft PR; send its number and head to batch runner 7 and to me. Report cap 20 lines, plus one Lessons line.
```
