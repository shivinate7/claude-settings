# Docs-only pull requests skip the code suites; PR runs skip duplicate work

## What was measured

gates-windows took about 12 min on a pull request. Two steps were repeats. The
unknown-read contract check reran all of `hooks/test_install_src.sh` (about 148 s on
Windows) for two cases. The Janitor sweep mutation harness ran on every OS.

## The ruling

- `hooks/test_install_src.sh` takes case names as arguments and runs only those. No
  arguments runs all. `lint/check_unknown_reads_contract.py` passes `caseF4 caseF6`.
  The cases keep one home.
- Janitor sweep mutation harness: on a pull request it runs on ubuntu only, as the
  Guard mutation harness already does. A push, the nightly run and a manual run keep it
  on every OS.
- `.github/scripts/harness-scope.sh` writes a third output, `code`. It is `false` only
  when the event is `pull_request`, the diff was read, and every changed file ends in
  `.md`. Any other case gives `true`: a push, a nightly run, a manual run, an unreadable
  diff, an empty diff, one non-`.md` file. The detector stays one script.
- When `code` is `false`, these skip: guard fixture suite, janitor sweep suite, janitor
  trigger suites, merge suites, installer suites (`install.sh`, `install.ps1`, pointer
  test), the unknown-read contract check, and both mutation harnesses.
- These always run: rule audit, ruling census, ruling home, stamp, STE lint, record
  slugs, and the other lints.
- Why the skipped suites are safe: grep of `hooks/test_guard.py`,
  `hooks/test_ruling_home.py` and `actions/stamp/test_stamp.mjs` found no read of the
  live `CLAUDE.md` or `decisions/`. Each builds its own fixture tree.
- main has no required status check (checked with the branch-protection API), so a
  skipped step cannot hang a pull request.

## Accepted risk

A skipped suite that reads a live `.md` file would miss a break on a pull request. The
nightly run and the push to main run everything, so the miss shows there.
