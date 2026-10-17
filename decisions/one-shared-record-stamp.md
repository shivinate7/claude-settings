# One shared parser, not four claim tools

## The ruling

`lint/rule_mechanisms.json` maps `git-slug-then-claim-number` to the refusal in `actions/stamp/stamp.mjs`
(`branchNumbered`). The merge tool, `merge/merge.py`, is the claim side. Other repos adopt both.

**One engine, generic.** One shared parser in claude-settings handles every repo's record format. Each
repo keeps a config file in its own tree. No repo gets its format rewritten. No existing record is ever
renumbered or renamed. `actions/stamp` names no repo: it describes record shapes, config fields and a
contract. Example configs are named for the shape they show. The README states the contract and the
checks that prove it. A behavior that only one repo needs becomes a config field with a generic name,
or the engine drops it. One adoption brief serves every repo, and the repo's own session measures its
own fields. A shape that no config field can state without naming one repo goes to the owner as a question.

Reason: a parent that holds one repo's facts goes stale when that repo changes. A shared engine also
re-gates a tree after a rejected push, which four separate tools do not.

**Adoption is each repo's job, later.** Each repo's own session writes its config and switches its own workflow.

**Formats built** (`actions/stamp/stamp.mjs`):

1. Number in frontmatter only (q_max, sharables).
2. Number in frontmatter and in the filename (job-cost-reporting).
3. Number in a heading, and for a split corpus in the filename too (banchi). It lives in
   `actions/stamp/formats/heading.mjs`; `stamp.mjs` only dispatches to it. Banchi's `regenerate` command
   appends to `ORDER.json` and rewrites the `CLAUDE.md` index.

**Left out, on purpose:**

- Build steps. Banchi numbers them by hand (`deferred/banchi-build-steps.md`). The engine refuses a tree with a pending step marker when the repo's config has an `unclaimed` entry for it. Banchi's config must carry that entry and its message.
- Debts: the claim tools have no debt kind.
- The flat-file fallback when `ORDER.json` is missing. The engine renames a claimed file with or without a manifest.
- The branch-side reads (`--stale`, `--unclaim`, `--landed`, `--porcelain`, `merging()`). This stamp claims only on the default branch.
- q_max's `docs/decisions/B*` and `G*` folders, and banchi's `docs/debts` and `T` prefix: no pending form yet.

**Deliberate differences from a repo's own claim tool:**

- A malformed pending heading (`## D012`, `## D-Bad_Slug`) is refused.
- A duplicate pending slug, or a pending file the filename rule cannot find, is refused.
- Path cites run longest slug first.
- The ceiling is read off the tree being stamped, not off `--ref`. At the merge, that tree is main.
- A rewritten file keeps its own line ending.
- A rename onto an existing file is refused before anything is written.
- A ref and HEAD with no merge base: `--stamp` reads no ref and never asks. `--check` off the default branch fails in GitHub Actions when it cannot read the base. Elsewhere it prints `UNKNOWN:` and exits 0.
- A failed `regenerate` stops the run and nothing is pushed.
- `--check` refuses a record numbered on a branch. **Adoption step:** banchi must retire the branch-side claim in `make merge` before it runs `--check`. Until then `--check` is red on every pull request `make merge` claims.

**Config fields stated, never guessed.**

- `numbering`: q_max takes the highest number plus one and never fills a gap. sharables and job-cost-reporting take the lowest number not taken. Read it from the repo's own claim tool.
- `cite.template`: q_max writes `D-nnn, Title`. job-cost-reporting writes `id, gloss`. sharables writes the bare id and enforces the gloss in its own citation check. No gloss is assumed.
- `regenerate`: a command that `--claim` runs after the claim, in the same commit. Each repo keeps its own generator (q_max `harness/decision-refs.mjs --gloss --write`, sharables `scripts/check_records.py --write-index`, job-cost-reporting its two generator scripts). The config only decides when it runs.

**`--check`.**

- On the default branch, only while something is pending, it asks: is every pending record one HEAD itself just added? A pending record waiting its turn is normal. One whose stamp run failed or whose push was rejected twice is not.
- Off the default branch, it reads the merge base of HEAD and the base ref. It refuses a number that the branch added or renamed.
- A branch may delete a numbered record. A number is never reused. A claim takes the next number past every number in the base tree and in the history of the base ref. It refuses a shallow or unreadable history, so a check job needs `fetch-depth: 0`.
- In a flat-file kind, a title change under one number is refused, because a swap looks the same. A title fix needs a delete and a new number.
- `stamp()` and a default-branch run with nothing pending read no history. `addedByHead` and the merge-order reader are lifted from `harness/decision-refs.mjs` nearly unchanged.

**Modes.** The action runs mode `check` only, with `contents: read`. No workflow writes to the default
branch. The claim runs before the merge, on the pull request branch, in `merge/merge.py`, and the PR's
own checks read the claimed tree. A pending record on the default branch fails `check`. The fix is any
pull request through the merge tool.

**Reopen** this entry on any of these. Do not guess a fourth format into `stamp.mjs`.

- Banchi asks to adopt.
- Banchi's tool learns to claim a step.
- A fifth repo has a shape the three formats miss.
- The `numbering` or `cite` assumption fails for a repo.

Fixtures: `actions/stamp/test_stamp.mjs` for the engine, `actions/stamp/test_action.sh` for the action's
shell logic. Both run in `gates`, `gates-windows` and `gates-macos` in `.github/workflows/gates.yml`.

Kind: process
Home: rule:git-slug-then-claim-number
Home: actions/stamp/stamp.mjs
