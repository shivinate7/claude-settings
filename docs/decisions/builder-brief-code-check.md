# A builder brief names the code check

## The ruling

Rule `builder-brief-code-check` in `hooks/guard.py` refuses an Agent or Task brief to a builder whose done check names no code check, in a repo whose checks workflow defines a job `checks`. Its home is `builder_code_check_hit` in `hooks/guard.py`, beside `brief_claim_hit`. Layer: the coordinator's order, 2026-11-08 10:19 CST (step `builder-brief-names-code-check`, a gap fix under owner item 410 a).

- The mistake (2026-11-08 10:11 CST, lane `lane-lint-cloud-time-limit`): the builder briefs for PRs #2017 and #2100 gave a done check of the touched suites, ruff and the STE lint. Both builders went green. `merge --lane-lint` then failed on the checks job's Code check step (dated comments) and on the comment narration check.
- The harm: a red branch reaches the batch runner as done. The join refuses it, or the batch CI run goes red and drops the lane, and the lane loses a round.
- The code check: `merge --lane-lint <head>`, which runs `bin/ci-job checks --lint` at that head (decision `lanes-run-no-full-ci-job`, a lane runs no full CI job). The brief may name either, or the checks job's Code check step alone (`code_check.py`), as the step title says. `BUILDER_CODE_CHECK` is the one pattern. It takes `merge`, `merge.cmd` or `merge/merge.py` before `--lane-lint`, and `ci-job` or `ci-job.cmd` before `checks --lint`. Tie tests read `--lane-lint` from `merge/merge.py`, `--lint` from `bin/ci-job` and `code_check.py` from `checks.yml`, so a rename at the source goes red.
- The done check: a line that starts with `Done check`, `Done when`, `Proof` or `Check that proves`, case-blind, then `:`, after an optional `-`, `*`, `#` or `**`. Blank lines right after the label are skipped. The section then runs to the next blank line or heading, and a fenced block is read whole. Only those sections count, so a brief that names the lint only as background ("fix what `merge --lane-lint` reported") with a test-only done check is refused. A brief with no label is read whole.
- Scope: the role `builder`, on an Agent or Task call. A reviewer, test-author, Explore or any other role passes. A Workflow `agent()` call is not read, as in `brief-claim-has-probe`.
- Other repos: `checks.yml` at the git top level must define a job `checks` directly under `jobs:`, the job that `ci-job checks` runs. A repo with no such file or job, a missing or unreadable file, and a payload with no `cwd` pass.
- The refusal names the remedy: add `merge --lane-lint <head>` to the done check. It names no forbidden target. It leaves out the `~/.claude/bin/` path, because a guard reason may not name `.claude`.
- The override lifts it (`owner-override`).
- Accepted limits: a brief that names the code check in its done check only to say "do not run it" passes. A label outside the four, such as "Done check, in order:" or "Done checks:", is not seen as a label, so the whole brief is read. `ci-job` with a flag between `checks` and `--lint` is not read as the code check. The `cwd` is the spawner's, so a session outside a checks repo that sends a builder into one is not judged. These are forms Claude is unlikely to write by mistake (`guard-guards-mistakes-only`).
- Unpinned edges, with no mutant: a name split inside a word across a line break, and an empty-string `cwd`. Also a `cwd` in a subfolder of the repo, and a nested `checks:` key deeper than the job indent.
- Cost: per builder spawn with a `cwd`, one short `git rev-parse --show-toplevel` process and one read of `checks.yml`, inside the guard call already running. Other spawns cost nothing. No file written, no log line beyond the refusal's own.

Protected by the 29 `builder-code-check:` cases in `hooks/test_guard.py`. The deny cases and the allow cases for new forms were red before the code that serves them. The rest are allow controls. The 23 mutants in `hooks/mutate_guard.py` labelled `builder-code-check:` each go red on one named case.

Kind: process
Home: hooks/guard.py
