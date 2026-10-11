# Merge needs no config file

## The question

Must a repo have `.github/stamp.json` before the merge tool works in it? Where does merge read
its settings from, and what does it do with a file that leaves fields out?

## The ruling

Owner, 2026-10-10:

1. Merge works in a repo with no config file. It uses the defaults below.
2. Merge reads all its settings (`defaultBranch` and the `merge` block) from the base branch's
   `.github/stamp.json` on origin. It never reads the local checkout or the PR's tree.
3. A file that exists but leaves out merge fields gets the defaults for those fields. A missing
   `defaultBranch` is read from the host. Merge prints one line that names the fields it filled.
4. An unknown field name in the `merge` block stops merge with one line that names it. So does
   a value of the wrong type: `deadlineMinutes` must be a whole number from 1 to 360 (the
   longest GitHub Actions job run), and each `ignoreChecks` entry needs a non-empty string
   name and reason.
5. A file that exists but is broken (bad JSON) stops merge with one line that names the file.
6. When the base loses its config or its stamp kinds during the wait, merge stops with one
   line, "base lost its config", and reverts its claim.
7. The "dirty tree" message names the checkout path it checked, in `merge/merge.py` and in
   the "checkout left as is" line of `merge/launch.py`.

## Incidents

- 5 of the owner's 8 repos have no `.github/stamp.json`. Merge stopped at the config read.
- ios-adblock, PR #28: the branch was made before the file existed. The claim step read the
  config from the PR's tree and printed a raw Node stack trace.
- ios-adblock: a `stamp.json` with a `merge` block and no `kinds` key made stamp.mjs throw
  "config.kinds must be an array".
- ios-adblock: a preview printed "dirty tree" while `git status --porcelain` was empty a moment
  later. Unmeasured: the likely cause is that the message does not name the checkout it checked.

## The defaults

- `defaultBranch`: from `gh repo view --json defaultBranchRef`.
- `merge.method`: `merge`.
- `merge.deadlineMinutes`: 45.
- `merge.requiredChecks`: `"protection"`. With no branch protection, merge stops with the
  existing remedy.
- `merge.afterMerge`: empty.

With no file, merge prints one line that says the defaults were used and names the file it
looked for.

## Related rules

- With no config, or a config with no `kinds` (missing or empty), merge skips the claim and the
  numbering check. stamp.mjs never runs.
- The check after the wait reads the config from the base tip fetched just now.
- A stamp.mjs failure prints one line: the reason and the path of a log with the full output.
  It never prints a stack trace.
- Known merge fields: `method`, `deadlineMinutes`, `requiredChecks`, `afterMerge`,
  `deleteBranch`, `ignoreChecks`.
- Bare `merge --unlock` takes the default branch from `origin/HEAD`, then from `gh`.
