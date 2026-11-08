# A builder brief names the code check

## The ruling

Rule `builder-brief-code-check` in `hooks/guard.py` refuses an Agent or Task brief to a builder that names none of `merge --lane-lint`, `ci-job checks --lint` and `code_check.py`, in a repo whose git top level holds `.github/workflows/checks.yml`. Its home is `builder_code_check_hit` in `hooks/guard.py`, beside `brief_claim_hit`. Layer: the coordinator's order, 2026-11-08 10:19 CST (step `builder-brief-names-code-check`, a gap fix under owner item 410 a).

- The mistake (2026-11-08 10:11 CST, lane `lane-lint-cloud-time-limit`): the builder briefs for PRs #2017 and #2100 gave a done check of the touched suites, ruff and the STE lint. Both builders went green. `merge --lane-lint` then failed on the checks job's Code check step (dated comments) and on the comment narration check.
- The harm: a red branch reaches the batch runner as done. The join refuses it, or the batch CI run goes red and drops the lane, and the lane loses a round.
- The code check: `merge --lane-lint <head>`, which runs `bin/ci-job checks --lint` at that head (decision `lanes-run-no-full-ci-job`, a lane runs no full CI job). The brief may name either, or the checks job's Code check step alone (`actions/code-check/code_check.py`), as the step title says. The names are tied to their sources: one test reads `--lane-lint` from `merge/merge.py`, and another reads `code_check.py` from `checks.yml`, so a rename goes red.
- Scope: the role `builder`, on an Agent or Task call. A reviewer, test-author, Explore or any other role passes. A Workflow `agent()` call is not read, as in `brief-claim-has-probe`.
- Other repos: a repo with no `checks.yml` has no code check to run, so its builder briefs pass. A payload with no `cwd` passes.
- The refusal names the remedy: add `merge --lane-lint <head>` to the done check. It names no forbidden target.
- The override lifts it (`owner-override`).
- Accepted limits: the whole brief is read, not its done-check section, since briefs label that section many ways (Proof, Done check, done when). A brief that names the code check only to say "do not run it" passes. These are forms Claude is unlikely to write by mistake (`guard-guards-mistakes-only`).
- Unpinned edges, with no mutant: a name split across a line break (whitespace is collapsed), an empty-string cwd, and a cwd in a subfolder of the repo (the top level is read through `guard_core._git`).
- Cost: per builder spawn with a cwd, one short `git rev-parse --show-toplevel` process and one stat of `checks.yml`, inside the guard call already running. Other spawns cost nothing. No file written, no log line beyond the refusal's own.

Protected by the `builder-code-check:` cases in `hooks/test_guard.py` (4 deny, 8 allow, 2 ties to the sources), whose 4 deny cases were red before the rule landed. The 9 mutants in `hooks/mutate_guard.py` labelled `builder-code-check:` each go red on one named case.

Kind: process
Home: hooks/guard.py
