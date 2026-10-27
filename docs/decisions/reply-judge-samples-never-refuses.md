# The reply judge samples, judges Input Needed, and never refuses

## The ruling

The Stop reply judge is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code.

- It judges 1 Stop in 5 (Stops 1, 6, 11, and so on; only Stops that carry a reply count), plus every Stop whose reply carries the Input Needed label (owner ruling 2026-10-25 23:40 CDT, "A"; it changes the sample-only ruling of 2026-10-13). The label is read in code from `LABEL_ORDER` in `lint/report_gate.py`; an item that is empty or "none" is not judged. Reason: a handed-off step with no reason and no check was the incident of Oct 25, the ios-adblock App IDs hand-off. Cost: one extra model call per report that carries Input Needed, no new file, no new process, no timer.
- Each finding writes one line to guard.log through `guard_core.record`. Named reader: the advisor at each cull, who counts flags against owner-confirmed misses and false alarms, to rule whether the judge stays, widens or goes. A failed write is swallowed. A judge line carries the judged style rule id, or `reply-judge` when the reason names none; the cull reads these with `lint/guard_log_report.py`, not the never-fired list.
- A damaged, missing or unwritable counter means that Stop is judged. It never refuses and never crashes (`gate-hooks-fail-closed`). A frozen counter therefore means judge every Stop (owner ruling 2026-10-13 17:52 CDT).
- The model call is `decision_watch.invoke_model`, the one home. Model and effort are the reply judge row of the model table (`agent-model-cap`).
- The model call starts a second `claude` program that does not share the app's login. Every hook that calls `invoke_model` logs in with a token from `claude setup-token`, saved in `~/.claude/state/hook-token` on each machine and never in the repository. The guard refuses writes to that folder, not reads (accepted risk, debt `token-read-accepted-risk`).
- A finding never refuses (owner ruling 2026-10-13 11:33 CDT). The hook runs `async: true` and passes the finding as a note at the start of the next turn. Reason: a refusal came after the owner had read the reply, so the session sent the reply twice. The report-shape gate still refuses.
- It fails open. An error, a timeout or an odd answer prints one stderr line and refuses nothing.
- The model call times out at 20 s. Three runs took 6.6, 7.0 and 8.0 s on the owner's machine, and the Stop entry in `settings.json` allows 25 s.
- Its rules are `output-start-with-point`, `style-cut-narration`, `output-never-paste-passing-output` and `output-never-hand-off-doable-step`. They stay `unmechanized` in `lint/rule_mechanisms.json` until the hook catches a real defect.

Kind: process
Home: hooks/reply_judge.py
