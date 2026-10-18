# Merge needs no config file

## The ruling

1. Merge works in a repo with no config file. It uses the defaults below.
2. Merge reads all its settings (`defaultBranch` and the `merge` block) from the base branch's
   `.github/stamp.json` on origin. It never reads the local checkout or the PR's tree.
3. A file that exists but leaves out merge fields gets the defaults for those fields. A missing
   `defaultBranch` is read from the host. Merge prints one line that names the fields it filled.
4. An unknown field name in the `merge` block stops merge with one line that names it. So does a value of
   the wrong type, null included. The types:
   - `method`: `merge`, `squash` or `rebase`. `deleteBranch`: true or false.
   - `deadlineMinutes`: a whole number from 1 to 360, the longest GitHub Actions job run.
   - `requiredChecks`: `"protection"`, or a non-empty list of non-empty strings.
   - `afterMerge`: a list of non-empty strings. `defaultBranch`: a non-empty string.
   - `ignoreChecks`: each entry needs a non-empty string name and reason.
5. A file that exists but is broken (bad JSON) stops merge with one line that names the file.
6. When the base loses its config or its stamp kinds during the wait, merge stops with one line, "base lost
   its config", and reverts its claim. The check after the wait reads the config from the base tip fetched
   just now.
7. The "dirty tree" message names the checkout path it checked, in `merge/merge.py` and in the "checkout
   left as is" line of `merge/launch.py`.

Defaults:

- `defaultBranch`: from `gh repo view --json defaultBranchRef`.
- `merge.method`: `merge`. `merge.deadlineMinutes`: 45. `merge.afterMerge`: empty.
- `merge.requiredChecks`: `"protection"`. With no branch protection, merge stops with the existing remedy.
- With no file, merge prints one line that says the defaults were used and names the file it looked for.

Related rules:

- With no config, or a config with no `kinds`, merge skips the claim and the numbering check. stamp.mjs
  never runs.
- A stamp.mjs failure prints one line: the reason and the path of a log with the full output. No stack trace.
- Bare `merge --unlock` takes the default branch from `origin/HEAD`, then from `gh`.

Reason: most of the owner's repos have no `.github/stamp.json`, and merge stopped at the config read.

Kind: build
Plan: decisions/merge-config-defaults.md#the-ruling (all)
Home: merge/merge.py
