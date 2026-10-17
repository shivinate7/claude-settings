# In CI, an unknown read is red; OS-independent gates run once

## The ruling

- A lint that cannot read its input prints UNKNOWN. Locally it exits 0. When env `CI` is set it exits non-zero, because the CI exit code is the verdict (`verification-report-unknown-reads`, report a read that could not run as unknown). Only `lint/check_record_slugs.py` has this shape. `harness-scope.sh` fails safe by running the harness. The other lints exit 1 on a failed read.
- OS-independent suites and pure lints run on ubuntu only: rule audit (suite and lint), record slugs, mod version bumps, landed dirs, agent models, STE lints, zizmor.
- The ruling census suite stays on every OS: it tests macOS `/var` symlinks and Windows backslash and `normcase` paths.
- Suites that touch paths, processes, shells, launchd, schtasks, symlinks or encoding run on every OS. When unsure, a suite stays on all OSes.
- `install.sh` syntax and checkout detection run once, on `shell-macos`. Windows keeps its own Git Bash run.
- `concurrency` cancels superseded runs on pull requests only. Push, nightly and manual runs finish.
- Step names do not change: `lint/rule_audit.py` reads them.

Why: a green exit on an unread input hides a defect, and a duplicate run costs minutes for no new verdict.

Accepted risk: a bug in an OS-independent suite that shows only on macOS or Windows is not caught. Unmeasured.

Kind: process
Home: .github/workflows/gates.yml
