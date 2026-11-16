# bin/duo-fold is the one fold for the iPhone Duo simulator

## The rulings

1. Owner ruling, Degen item 187, 2026-11-09 20:16 CST: the Home repo's `scripts/duo-fold.sh` at commit `e7f2b5d6` becomes a claude-settings tool, `bin/duo-fold`, next to `bin/sim-test` and `bin/sim-lease`. Every repo that uses the iPhone Duo calls it. Until this merges, Degen and Home keep their copies (owner, 2026-11-09 20:22 CST).
2. `bin/duo-fold <udid> <folded|open>` folds the Duo with `hinge`, reads the angle back, and refuses unless it is within 0.5 of 0 (folded) or 180 (open). Exit 0: the angle passes. Exit 1: a refusal, with a `duo-fold:` line on stderr saying why. Exit 64: wrong arguments, and hinge is not called. A hinge move that exits non-zero is noted on stderr, and the angle is still read. No retry. The tool runs only on an arm64 Mac; any other machine exits 1 before hinge is fetched or run. With `HINGE` unset, it fetches hinge v0.3.0 at the pinned commit `afb8f0bd277cb12187f0844a79542cbac35e7385`.
3. One home. `bin/duo-fold` is the only copy of the Duo fold. Degen and Home call it and keep no copy once they switch.
4. Cost, per call: one `uname -m`, one `awk` for the tolerance check, one hinge move and one `hinge get`. With `HINGE` unset, also a `git` clone once under `DUO_FOLD_WORK`, then a `git checkout` of the pin on each call. A log file is written only when `DUO_FOLD_LOG` is set; unset, hinge's output goes to stderr. Hinge's own helper compiles once on first use into `~/.cache/hinge`, and again when its source or Xcode changes (read from hinge at the pinned sha; not run here) (unmeasured). No daemon, no timer.

Test: `lint/test_duo_fold.sh`, with stubbed `uname`, `hinge` and `git`. It checks the exit codes, the 0.5 tolerance, no retry after a failed move, the arm64 refusal before any fetch or hinge call, and wrong arguments.

Not proven here: there is no Mac or simulator in the cloud. The real text that `hinge get` prints, and whether the Duo folds, are untested here. The stubs write the angle in the form the tool expects. The clone and checkout of the pinned hinge are stubbed too, so the real pin is not fetched here.

Dated by: a new hinge pin in `bin/duo-fold`, or a change to its exit codes. The iOS skill section (`skills/ios-apps/SKILL.md`, "Folding the iPhone Duo simulator") repeats both.

Kind: process
Home: bin/duo-fold
