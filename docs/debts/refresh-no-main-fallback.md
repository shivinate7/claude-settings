# Installer refresh does not fall back to main

- **What.** When origin has no `stable` branch, an existing cloud clone or mirror keeps its old files with a WARN, and the own-checkout fetch leaves the checkout as it is. Only the clone step and the tarball fall back to `main`. The install is stale but safe. This departs from the pick to pin main with one WARN (orchestrator pick, lane merge-flow-after-anthropic, 2026-11-12). Act 1 of that lane merges first.
- **Where.** `install.sh`: the `mirror_refresh` function (about line 393) and the own-checkout fetch block (about lines 506-556). The fallback is `fall_back_to_main` (about line 442), used by `clone_mirror` and the tarball path.
- **Decision.** `merge-reinstalls-from-main` (item 6: a failed fetch warns, then the install goes on).
- **Retire.** Make `mirror_refresh` and the own-checkout fetch fall back to `main` with one WARN, as `clone_mirror` does. The case for each path in `hooks/test_install_src.sh` then shows it closed.
