---
id: pending
slug: verified-trailer
---

# A commit says how it was verified, in a Verified line

## The ruling

Each non-merge, non-revert commit on a lane carries a Verified line in its message. The line takes one of two forms:

- `Verified: <command> -> <verdict>`. The command proved the commit. The verdict is free text, so `-> PASS` and `-> FAIL` both pass.
- `Verified: none: <reason>`. No command ran. The reason is not empty.

1. `lint/check_red_run.py` reads the lines in observe mode. Its `main()` calls `verified_gaps()` on the rows that `commits()` already read. A commit with no valid line prints `check_red_run: OBSERVE: <sha> <subject>: no valid Verified line`. The exit code stays 0, because only a Red-run gap sets exit 1. A line counts wherever it sits in the message (`has_verified()`).
2. The read starts at a rollout. `verified_gaps()` judges a commit only when the check file at HEAD holds `VERIFIED_ROLLOUT` (`verified-trailer-rollout-1`), and the commit's parent holds it too. `rollout_landed()` reads git's trees with `git grep`, never the disk. A repo whose check file lacks the marker judges nothing, so child repos stay off. A commit from before the marker landed is not judged. Renaming the check file turns the read off.
3. Not judged: a merge (`commits()` reads non-merge commits only), a revert (the `REVERT` line), and a root commit.
4. `gaps()` and `judge()` never read a Verified line. The push guard calls them in every repo, so a push is never refused on a Verified line.
5. `merge/merge.py` `commit_claim()` writes the line on its own commits. The claim commit carries `VERIFIED_CLAIM`. A page-only commit carries `VERIFIED_PAGE`. Both are `Verified: none: <reason>`.
6. CI runs the read in the step "Red-run trailer" of `.github/workflows/checks.yml`. That step runs only when `lint_red_run` is set. `.github/scripts/ci-scope.sh` sets it for a non-.md path, or for a .md path under a test folder. A docs-only pull request reads no Verified line.
7. No refusal is built. No commit-time, push-time or merge-time check refuses a commit for a missing line. A refusal needs its own ruling, after the observe run.

## Known limits

- The check reads that a valid line is present. It does not read that the command ran, or that the verdict is true. A reviewer reads each line.
- Observe mode fails nothing. A commit with no line stays as it is until a refusal exists.
- A gap prints no remedy. The check prints `REMEDY` only for a Red-run gap.
- Item 6 holds. A docs-only pull request is never read.

## Mistake, harm and why

Mistake (unmeasured): a lane commit lands with no record of the command that proved it, or of whether one ran.

Harm: a reviewer cannot tell a checked commit from an unchecked one without a re-run.

Why: the Red-run line records the proof of a test commit. The Verified line covers each other lane commit, so every lane commit states its proof. Observe mode shows each gap in the CI log and blocks no lane.

Source: the coordinator's brief for the verified-trailer lane, 2026-11-18.

## Cost

No long-lived process, log file or timer. Each check run starts one `git log --numstat` for the range, shared with the Red-run read. It also starts one `git grep -q` on HEAD's check file, and one on the parent of each commit with no valid Verified line that is not a revert. Each is a short child process (unmeasured; no test counts these starts).

Kind: process
Home: lint/check_red_run.py
