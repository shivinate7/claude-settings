# A record's Facts line is checked against live facts

## The ruling

Owner, 2026-11-15 11:27 CST, option b, on the consultant's design question. The question was how a check reads a `State:` claim without reading prose. A decision record may carry one `Facts:` line, in the exact form `Facts:` at column 0, directly under its `State:` line. Claims are split by `;`. Two kinds are allowed: `pr <N> open` or `pr <N> merged` (the pull request of this repo), and `ref <name> present` or `ref <name> absent` (a branch on this repo's origin).

The check reads that line only. It never reads the words of `State:` (decision, PR 3476, held: a check keyed on prose words alone cries wolf). A record with no `Facts:` line is not checked.

State: live in the check, step 3 of `actions/claude-md-cites`. No record carries a `Facts:` line yet. Measured on main, 2026-11-15: 9 `State:` lines, 3 name a checkable fact, 2 of those 3 were wrong (`stable-branch`, `stable-fallback-warn`).

- Unreadable fact (no token, HTTP error, bad reply, a repo the token cannot read, an unclosed fence): exit 2, unknown, never green.
- A line that is Facts-like but not the exact form, a second Facts line, a non-blank line right under the Facts line, an unknown claim form (a count such as "211 commits behind"), an empty claim: exit 1, with file and line.
- Lines in a code fence are never read.
- Open and not ruled: whether a child repo's token can read this repo's pull requests. If claude-settings is private, a child run goes red as unknown at the first `pr` claim. Wiring option b is in place: the step stays in the action. Options a (run only in this repo's CI) and c (child warns only) wait for the owner.

Why: a `State:` line goes stale when a pull request merges or a branch appears, and no reader catches it. A named PR number or branch is a fact a REST read settles.

Kind: build
Home: lint/compliance_probes.py
