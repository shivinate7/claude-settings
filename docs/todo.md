# Todo

Tasks a session caught and did not do. One line each.

- Merge c136, one page per repo (waiting on you first, the roadmap below). Owner asked its status Oct 28 13:04 CDT and Oct 29 13:44 CDT. Lane started Oct 29.
- Align each child repo (banchi, q_max, home, mailaudit, degen) with claude-settings main, under grant item 2 a. Fix lanes started Oct 29 (owner asked 13:45 CDT); each repo's PR needs its batch runner to merge.
- fb-1520-1: Running /autocompact writes the chosen window into the user settings file. In the pinned checkout that file is the tracked settings.json, so the repo shows a stray change (measured Oct 28, Claude Code 2.1.312). Keep that write off the tracked file. The hook half is done: the handoff hook reads the window in use (decision precompact-handoff, item 1). Roadmap step c203 (compact window off the tracked file) is marked done, but only the hook half shipped. The fix route waits on the owner's answer to waiting-page item 61 (per-tier context limits, still open); its option c is a settings.json copy made at install.
- fb-0359-2: Re-run the compliance probes on q_max and mailaudit main, with `compliance_probes.py <probe> <root>` from claude-settings main. Send triage the r1 lanes still open (mailaudit lanes 1-5, q_max lanes 2-7 and 9). The r1 reports of Oct 30 00:01 and 00:07 CDT predate later merges.
- Measure one step down per role (roadmap step c201, measure helper-agent cost): one lane per role on the lower model, same brief shape, compared with the numbers in the Measured part of `agent-model-cap` (the model-per-role table).
- Redraw the waiting-page mockups in docs/design (waiting-page.html, one-page.html and the c190, c193 and c204 pages) without the Add a note and Take my pick buttons (steps note-always-open and drop-take-pick, PR #872).
- Rewrite the hooks/test_guard.py fixture text "Take my pick, then press Send." to name a control the waiting page still has (step drop-take-pick, PR #872).
- Port the always-open note box and the dropped Take my pick button to each other repo's waiting page (step notes say "Port: yes", PR #872).
- fb-1511-1: Setup script installs claude-settings before a cloud session starts (waiting item 77, pick a; owner 2026-10-30 15:09 CDT). Lane setup-script-install builds cloud-setup.sh, its test and the README paste block. After merge, the owner pastes the block once per environment and runs one fresh-session test: a bare builder spawn reports Sonnet.
- fb-1417-2: c95 part 2, robust timing asserts (branch c95-robust-timing-asserts, draft PR #896), queued for batch 39; remove this line when it lands.
