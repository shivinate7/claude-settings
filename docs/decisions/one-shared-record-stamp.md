# One shared parser, not four claim tools

## The ruling

One shared parser in claude-settings handles every repo's record format. Each repo keeps a config file in its
own tree. No repo gets its format rewritten. No existing record is ever renumbered or renamed. `actions/stamp`
names no repo: it describes record shapes, config fields and a contract. The merge tool gets no
setting that names a repo's own claim command. A behavior that only one repo needs
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

Kind: process
Home: rule:git-slug-then-claim-number
Home: actions/stamp/stamp.mjs
