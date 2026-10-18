# One shared parser, not four claim tools

## The ruling

One shared parser in claude-settings handles every repo's record format. Each repo keeps a config file in its
own tree. No repo gets its format rewritten. No existing record is ever renumbered or renamed. `actions/stamp`
names no repo: it describes record shapes, config fields and a contract. A behavior that only one repo needs
becomes a config field with a generic name, or the engine drops it. A shape that no config field can state
without naming one repo goes to the owner as a question. Do not guess a fourth format into `stamp.mjs`.

Reason: a parent that holds one repo's facts goes stale when that repo changes. A shared engine also re-gates a
tree after a rejected push, which four separate tools do not.

- Read each config field (`numbering`, `cite.template`, `regenerate`) from the repo's own claim tool. Never
  guess one. A gloss in `cite.template` comes from the config only.
- A number is never reused.
- The action runs mode `check` only, with `contents: read`. No workflow writes to the default branch. The claim
  runs before the merge, on the pull request branch, in `merge/merge.py`. A pending record on the default branch
  fails `check`. The fix is any pull request through the merge tool.
- Other repos adopt the stamp and the merge tool, each in its own session.
- Owner, 2026-10-06: claude-sharables moves its claim onto the stamp. The `merge` tool gets no setting that names a repo's own claim command. Unmeasured: whether the stamp can write sharables' ids, which have no hyphen and no padding (`D93`); if not, that is a stamp change here first. Revisit at sharables' next claim of a record id, or the next stamp change.
- Owner, 2026-09-25: Banchi build steps (`` 0. `step <slug>` `` lines in `docs/gates/steps/`) stay out of the stamp. Banchi's `claim-ids.py` reads a pending step only from `docs/GATES.md`, now a pointer, so no working rule exists to copy. Revisit when `claim-ids.py` claims a step in `docs/gates/steps/`; then copy its rules and prove parity as for decisions. Until Banchi's own config carries an `unclaimed` entry for a step marker, a pending step passes in silence.
- Owner, 2026-09-28: the stamp check uses full history (`fetch-depth: 0`) for now. A depth-1 checkout of a pull request merge commit has no parents, so `stamp.mjs --check` off the default branch cannot find the merge base. Unmeasured idea: use the first parent of the merge commit as the base with `fetch-depth: 2`, after a fixture makes a shallow clone of a real two-parent merge commit. Revisit when a repo reports its full-history checkout is too slow.

Kind: process
Home: rule:git-slug-then-claim-number
Home: actions/stamp/stamp.mjs
