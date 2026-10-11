# Merge needs no config file

## The question

Must a repo have `.github/stamp.json` before the merge tool works in it?

## The ruling

Owner, 2026-10-10: no. Merge works in a repo with no config file. It uses the defaults below.
A file that exists but is broken still stops merge, with one line.

## Incidents

- 5 of the owner's 8 repos have no `.github/stamp.json`. Merge stopped at the config read.
- ios-adblock, PR #28: the branch was made before the file existed. The claim step read the
  config from the PR's tree and printed a raw Node stack trace.

## The defaults

- `defaultBranch`: from `gh repo view --json defaultBranchRef`.
- `merge.method`: `merge`.
- `merge.deadlineMinutes`: 45.
- `merge.requiredChecks`: `"protection"`. With no branch protection, merge stops with the
  existing remedy.
- `merge.afterMerge`: empty.

Merge prints one line that says the defaults were used and names the file it looked for.

## Related rules

- With no config, or a config with no `kinds`, merge skips the claim and the numbering check.
  stamp.mjs never runs.
- The claim and the numbering check read the stamp config from the base branch, never from
  the PR's tree. This includes the check after the wait. The merge settings come from the
  checkout merge runs in.
- A stamp.mjs failure prints one line: the reason and the path of a log with the full output.
  It never prints a stack trace.
