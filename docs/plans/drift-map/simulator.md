# Simulator drift table (pilot)

Gold is the parent value (claude-settings), not proven truth. Cells: `absent` = repo read, fact not stated. `gap` = repo not reachable, not read. `no home` = the parent states no value. Pinned shas are in [README.md](README.md).

| fact | gold (parent) | claude-settings | q_max | banchi | degen | joyous | mailaudit | home | ios-adblock | mac-memory | verdict | direction | cites | what good looks like |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| which-duo | no home | absent | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | none | none yet: parent has no home |
| hinge-version | artemnovichkov/hinge at commit abd539d6, installed at ~/.local/bin/hinge (skills/ios-apps/SKILL.md:46) | abd539d6 (SKILL.md:46) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | skills/ios-apps/SKILL.md:46 | artemnovichkov/hinge at commit abd539d6, installed at ~/.local/bin/hinge (skills/ios-apps/SKILL.md:46) |
| screenshot-names | no home | absent | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | none | none yet: parent has no home |
| lock | folder ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock, pid in file named pid (bin/sim-test:7); state/sim-test.lock under the config folder, Mac-wide (README.md:283) | sim-test.lock, Mac-wide (bin/sim-test:7; README.md:283) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | bin/sim-test:7; README.md:283 | folder ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock, pid in file named pid (bin/sim-test:7); state/sim-test.lock under the config folder, Mac-wide (README.md:283) |
| confirm-timeout | unmeasured (docs/debts/notes.md:371) | unmeasured (docs/debts/notes.md:371) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | docs/debts/notes.md:371 | unmeasured (docs/debts/notes.md:371) |
| after-boot | no home | absent | absent | absent | boots one and shuts it down after the test (README.md:94) | absent | absent | gap | gap | gap | local-nuance | undated | degen README.md:94 | none yet: parent has no home |
| erase | no home | absent | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | none | none yet: parent has no home |
| other:hinge-commands | hinge -d <udid> open\|close\|half\|<degrees>\|get\|posture (skills/ios-apps/SKILL.md:49) | same (SKILL.md:49) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | skills/ios-apps/SKILL.md:49 | hinge -d <udid> open\|close\|half\|<degrees>\|get\|posture (skills/ios-apps/SKILL.md:49) |
| other:test-diagnostics-flag | sim-test passes -collect-test-diagnostics never (skills/ios-apps/SKILL.md:23) | same (SKILL.md:23) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | skills/ios-apps/SKILL.md:23 | sim-test passes -collect-test-diagnostics never (skills/ios-apps/SKILL.md:23) |
| other:lock-poll-seconds | 2 (docs/decisions/sim-test-is-the-one-boot-path.md:8) | 2 (same file) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | docs/decisions/sim-test-is-the-one-boot-path.md:8 | 2 (docs/decisions/sim-test-is-the-one-boot-path.md:8) |
| other:sweep-stop-cap | SIM_SHUTDOWN_CAP = 4 (janitor/sweep.py:1775) | 4 (sweep.py:1775) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | janitor/sweep.py:1775 | SIM_SHUTDOWN_CAP = 4 (janitor/sweep.py:1775) |
| other:sweep-idle-age | booted 1 hour or more ago (docs/decisions/sweep-shuts-down-idle-simulators.md:9); SIM_IDLE_SECONDS = 3600 (janitor/sweep.py:1774) | 1 h / 3600 s (decision:9; sweep.py:1774) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | docs/decisions/sweep-shuts-down-idle-simulators.md:9; janitor/sweep.py:1774 | booted 1 hour or more ago (docs/decisions/sweep-shuts-down-idle-simulators.md:9); SIM_IDLE_SECONDS = 3600 (janitor/sweep.py:1774) |
| other:boot-record-path | state/sim-boots.jsonl (docs/decisions/sweep-shuts-down-idle-simulators.md:7) | same (decision:7) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | docs/decisions/sweep-shuts-down-idle-simulators.md:7 | state/sim-boots.jsonl (docs/decisions/sweep-shuts-down-idle-simulators.md:7) |
| other:boot-cap | 2 devices of any kind booted (README.md:282) | same (README.md:282) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | README.md:282 | 2 devices of any kind booted (README.md:282) |
| other:shared-simulator | shared iPhone 18 Pro (README.md:281) | same (README.md:281) | absent | absent | absent | absent | absent | gap | gap | gap | same | undated | README.md:281 | shared iPhone 18 Pro (README.md:281) |
| other:test-runtime | no home | absent | absent | absent | iOS 27.1 simulator runtime (docs/specs/plan.md:1423) | absent | absent | gap | gap | gap | local-nuance | undated | degen docs/specs/plan.md:1423 | none yet: parent has no home |
| other:sim-device-name | no home | absent | absent | absent | Degen iPhone (docs/specs/plan.md:2189); Degen simulator (docs/debts/clear-alert-close-unmeasured.md:7) | absent | absent | gap | gap | gap | local-nuance | undated | degen docs/specs/plan.md:2189; degen docs/debts/clear-alert-close-unmeasured.md:7; README.md:281 | none yet: parent has no home |
| other:folded-duo-taps-dead | no home | absent | absent | absent | XCUITest taps on the folded Duo sim do nothing; folded results unknown (docs/debts/duo-folded-uitest-taps-dead.md:3) | absent | absent | gap | gap | gap | local-nuance | undated | degen docs/debts/duo-folded-uitest-taps-dead.md:3 | none yet: parent has no home |
| other:hinge-poses | no home | absent | absent | absent | absent | absent | hinge -d <udid> open\|half\|close (measurements/duo-fold-and-keyboard.md:12) | gap | gap | gap | local-nuance | undated | mailaudit measurements/duo-fold-and-keyboard.md:12; skills/ios-apps/SKILL.md:49 | none yet: parent has no home |
| other:device-hub | no home | absent | absent | absent | absent | absent | never drive Device Hub (measurements/duo-fold-and-keyboard.md:23) | gap | gap | gap | local-nuance | undated | mailaudit measurements/duo-fold-and-keyboard.md:23 | none yet: parent has no home |
| other:duo-classes-not-in-ci | no home | absent | absent | absent | absent | absent | DuoHandUITests DuoSpreadUITests DuoShellUITests skipped by native-check and hosted runs; owner runs by hand (Makefile:16) | gap | gap | gap | local-nuance | undated | mailaudit Makefile:16 | none yet: parent has no home |

Verdict count over 21 rows: same 14, local-nuance 7, unconfirmed 0. No row is drifted, so no row has a lane.

## Not read

- Unreachable: home `records/duo-simulator.md`, ios-adblock, mac-memory `degen duo-sim-fold`. Every cell for them is `gap`.
- claude-settings: not read `lint/test_sim_test.sh`, `hooks/test_guard.py`, `hooks/test_sim_boot_record.py`, `janitor/test_sweep.py`. `hooks/guard.py` read only at line 3563 (`SIM_BOOT_CAP = 2`). Term `AC2E94F9` has no hit, so which-duo is unknown.
- degen: not read the hinge code in `native/**/*.swift` beyond identifiers, nor `tools/ios-ship.json` and other data JSON. No value found for screenshot-names, confirm-timeout or erase.
- mailaudit: not read in full `docs/design/duo-blind/*.html`, `test/ci-wiring.test.mjs`, `native/ManifestUITests/DuoSpreadUITests.swift`, `native/ManifestUITests/DuoHandUITests.swift`.
- q_max, banchi, joyous: nothing left unread.

## Writer check against the claude-settings source

Four cells above differ from the text at the pinned sha. They are reader misses, not drift. No lane follows from them.

- screenshot-names: `skills/ios-apps/SKILL.md:51` names `--display=LCD` for the outer screen and `--display=LCD-1` for the inner one. The cell says `absent`.
- confirm-timeout: `skills/ios-apps/SKILL.md:50` says to read `posture` when `-t 6` times out. The cell cites `docs/debts/notes.md:371`, which says boot check timeouts are unmeasured. That is a different fact.
- lock: the table cites `sim-test.lock` in `bin/sim-test:7`. The older fixture says claude-settings has no lock. Main has since added the lock.
- after-boot: `skills/ios-apps/SKILL.md:53` says the outer screen may not update after the first `close`: open and close again. The row says the parent has `no home`, so the degen cell was read as a child addition.
