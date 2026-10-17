# One shared parser, not four claim tools

## The ruling

`lint/rule_mechanisms.json` maps `git-slug-then-claim-number` to the refusal in `actions/stamp/stamp.mjs`
(`branchNumbered`). The merge tool, `merge/merge.py`, is the claim side. Other repos adopt both.

**One engine, generic.** One shared parser in claude-settings handles every repo's record format. Each
repo keeps a config file in its own tree. No repo gets its format rewritten. No existing record is ever
renumbered or renamed. `actions/stamp` names no repo: it describes record shapes, config fields and a
contract. Example configs are named for the shape they show. A behavior that only one repo needs becomes
a config field with a generic name, or the engine drops it. One adoption brief serves every repo, and the
repo's own session measures its own fields. A shape that no config field can state without naming one
repo goes to the owner as a question.

Reason: a parent that holds one repo's facts goes stale when that repo changes. A shared engine also
re-gates a tree after a rejected push, which four separate tools do not.

**Adoption is each repo's job, later.** Each repo's own session writes its config and switches its own workflow.

**Three formats.**

1. Number in frontmatter only.
2. Number in frontmatter and in the filename.
3. Number in a heading, and for a split corpus in the filename too (`actions/stamp/formats/heading.mjs`).

**Left out, on purpose.** Build steps (the engine refuses a tree with a pending step marker when the
repo's config has an `unclaimed` entry for it). Debts. The flat-file fallback when `ORDER.json` is
missing. The branch-side reads (`--stale`, `--unclaim`, `--landed`, `--porcelain`, `merging()`): this
stamp claims only on the default branch. Folder and prefix forms with no pending form yet.

**Config fields stated, never guessed.** `numbering` (highest plus one, or lowest not taken), `cite.template`
(no gloss is assumed) and `regenerate` (a command that `--claim` runs after the claim, in the same
commit). Read each from the repo's own claim tool.

**Rules of the engine.**

- A malformed or duplicate pending slug, a pending file the filename rule cannot find, and a rename
  onto an existing file are refused before anything is written.
- The ceiling is read off the tree being stamped. At the merge, that tree is main.
- A failed `regenerate` stops the run and nothing is pushed.
- A number is never reused. A claim takes the next number past every number in the base tree and in the
  history of the base ref. It refuses a shallow or unreadable history, so a check job needs
  `fetch-depth: 0`. A branch may delete a numbered record.
- In a flat-file kind, a title change under one number is refused, because a swap looks the same. A title
  fix needs a delete and a new number.

**`--check`.**

- On the default branch, only while something is pending, it asks: is every pending record one HEAD itself
  just added? A pending record waiting its turn is normal. One whose stamp run failed or whose push was
  rejected twice is not.
- Off the default branch, it reads the merge base of HEAD and the base ref. It refuses a number that the
  branch added or renamed. **Adoption step:** banchi must retire the branch-side claim in `make merge`
  before it runs `--check`.
- With no merge base, `--stamp` reads no ref and never asks. `--check` off the default branch fails in
  GitHub Actions when it cannot read the base. Elsewhere it prints `UNKNOWN:` and exits 0.

**Modes.** The action runs mode `check` only, with `contents: read`. No workflow writes to the default
branch. The claim runs before the merge, on the pull request branch, in `merge/merge.py`, and the PR's
own checks read the claimed tree. A pending record on the default branch fails `check`. The fix is any
pull request through the merge tool.

**Reopen** this entry on any of these. Do not guess a fourth format into `stamp.mjs`.

- Banchi asks to adopt.
- Banchi's tool learns to claim a step.
- A fifth repo has a shape the three formats miss.
- The `numbering` or `cite` assumption fails for a repo.

Kind: process
Home: rule:git-slug-then-claim-number
Home: actions/stamp/stamp.mjs
