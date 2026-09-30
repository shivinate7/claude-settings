---
name: ci-hygiene
description: Use when a session creates or edits CI config (GitHub Actions, workflow files, .github/workflows, other CI files), or when the user says CI is slow, queued, or flaky, or says "ci-hygiene". Not for ordinary code edits. Keeps CI fast, cheap, and trusted.
---

Written for GitHub Actions. The same ideas apply to other CI systems. Commands and YAML are in
`snippets.md` in this skill folder. Read it when you write the config.

## Procedure

1. **Measure first.** Rank the step times of a finished run. Optimize the slowest step only.
   Never guess which step is slow.
2. **Check what exists.** Read the current workflow and the log before you build a speedup. The
   step may already run in parallel, or be cached.
3. **Gate slow checks on their inputs.** Run a slow check after a change to the files it reads.
   Detect the change with `git diff` against the base commit. Add a nightly full run and a manual
   trigger. If detection cannot read the diff, run the check (fail safe).
4. **Cancel superseded runs.** Set `concurrency` with `cancel-in-progress`, so a new push to a
   ref cancels the old run on that ref. Runners with a low concurrency cap, such as hosted
   macOS, queue first.
5. **Cap each job's time.** Set `timeout-minutes` on each job at about 2x its slowest green run.
   Give a network step, such as a browser install, its own short cap.
6. **After a merge, read every run the push starts.** A deploy or nightly workflow is not a
   required check, so its failure shows on no PR.
7. **Pin and audit actions.** Pin each third-party action by full commit SHA, with the version as
   a comment. Let a bot keep the pins current. Disable credential persistence on checkout. Run
   an audit tool in CI, and run it locally with the exact CI command and paths.
   If the installed tool's `--version` matches the CI pin, use it. If it does not, install a copy.
8. **Batch green PRs.** Merge PRs that are green together through one integration branch. One CI
   run then covers the combined code. "No conflicts" does not prove they work together.
9. **Wait without loops.** Watch a run once, in the background, and keep its output. Never poll
   with a sleep loop.
10. **Prove each new gate red once.** Break the gate's target on a scratch copy. Watch the gate
   fail. Restore the target. A gate you did not see go red is not proven.

## Before you skip a required job

Branch protection decides if a skipped job counts as passing. Read the protection rules first.
See `snippets.md`.

## Docs

CI claims in README or docs go stale too. See the `fresh-prose` skill.
