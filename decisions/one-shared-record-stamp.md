# One shared parser, not four claim tools

CLAUDE.md: "Never allocate a numbered record on a branch. Write a slug. Claim the
number at merge." (rule `git-slug-then-claim-number`.) `lint/rule_audit.py` reads that
rule as `unmechanized` here. Its own reason: "README Decision 5 keeps id-claiming
manual and per repo, on purpose." That reason still stands. This entry is not the
mechanism for claude-settings. It is the mechanism other repos can adopt.

## What was measured, 2026-09-24

Only q_max enforces this rule with a CI stamp. `.github/workflows/stamp.yml` calls
`harness/decision-refs.mjs --stamp`. Before that stamp existed, D-272 was claimed
three times in q_max's own log. D-273 through D-276 were each claimed twice. Every
other repo still claims numbers by hand, at merge, with its own tool:
`claude-sharables scripts/check_records.py --claim-ids`, `job-cost-reporting
toolchain/claim_ids.py`, `banchi scripts/claim-ids.py`.

Four repos, four record shapes, all serving the same one-sentence rule:

- q_max: `id: pending` in frontmatter becomes `id: D-042`. One file per record.
- sharables: the same frontmatter shape, but no hyphen and no padding. `id: pending`
  becomes `id: D93`. Three kinds: `decisions`, `findings`, `gaps`.
- job-cost-reporting: the number lives in the frontmatter and in the filename.
  `_<date>-<slug>.md` becomes `D12_<date>-<slug>.md`. Four kinds: `docs/decisions`,
  `docs/build`, `docs/findings`, `docs/questions`.
- banchi: the number lives in a heading. For `docs/decisions` it also lives in the
  filename. MEASURED on banchi `main` (053acf0), 2026-09-24. `docs/decisions` holds 262
  entries: 257 numbered files, 4 `_*.md` section files, and `ORDER.json`.
  `docs/decisions/D-<slug>.md`, first line `## D-<slug> — Title`, becomes
  `D258-<slug>.md` with `## D258 — Title`. The filename pads to 3 digits. The heading
  does not. `docs/CODES-DECISIONS.md` is a live flat corpus, `C1` to `C11`, one heading
  per record, no rename. `docs/DECISIONS.md`, `docs/GATES.md` and `docs/DEBTS.md` are
  pointer files. Each says so on its own first lines. `docs/debts` holds 35 entries
  (33 numbered, `_preamble.md`, `ORDER.json`). `docs/gates/steps` holds 25 (23 steps and
  2 `_*.md`), with no `ORDER.json` of its own. `docs/gates/ORDER.json` lists them.
  `docs/gates/contract` holds 11. Its own claim tool, `scripts/claim-ids.py`, is 1727
  lines.

## The choice

The owner decided this on 2026-09-24. One shared parser in claude-settings handles
every repo's record format. Each repo keeps a config file in its own tree. No repo
gets its format rewritten. No existing record is ever renumbered or renamed.

**The runner option it beat.** A thin runner could call each repo's own claim tool
instead. That would need no new parser at all. It was refused for two reasons. It
keeps four separate implementations of one rule, free to drift apart. And it still
misses a defect all four share: nothing re-gates a tree after a rejected push forces a
retry. A shared engine fixes that once, for every repo that adopts it.

**Adoption is each repo's own job, done later.** This entry and `actions/stamp/` build
the tool. They do not touch q_max's, sharables', or job-cost-reporting's own trees.
Each repo's own Claude session writes its own config later. Each switches its own
workflow over, on its own schedule.

## Formats built, and left out

`actions/stamp/stamp.mjs` covers three shapes:

1. Number in frontmatter only (q_max, sharables).
2. Number in frontmatter and in the filename (job-cost-reporting).
3. Number in a heading, and for a split corpus in the filename too (banchi). Its own
   module, `actions/stamp/formats/heading.mjs`. `stamp.mjs` only dispatches to it.

Format 3 was read rule by rule off `scripts/claim-ids.py`, `scripts/index-decisions.py`
and `scripts/decisions_corpus.py`. The numbered rule list, each rule marked covered or
left out, is in the pull request body. The engine takes banchi's decisions and code
cards. banchi's own `scripts/index-decisions.py --write` runs as the `regenerate`
input. It appends to `ORDER.json` and rewrites the `CLAUDE.md` index.

**Parity, MEASURED 2026-09-24.** Two untouched copies of banchi main got the same
pending records: 2 decisions, 1 code card, 1 step, and cites from 8 other files. One
copy ran `claim-ids.py --write`. The other ran the action's own `run.sh`, with the
env `action.yml` passes it and `REGENERATE_COMMAND` set to banchi's command. The two
trees matched byte for byte, 1245 of 1245 files. A second
run, with one pending name listed in `ORDER.json`, matched 1245 of 1245 too.

**Left out, on purpose:**

- **Build steps.** claim-ids.py reads a pending step only from `docs/GATES.md`, which
  is now a pointer file. MEASURED: a pending step in `docs/gates/steps/` gets no claim.
  The same step written into `docs/GATES.md` is claimed as `step 1`, because that file
  holds no numbered step, so the ceiling reads 0. Step 1 already exists. banchi's own
  tool is stale for steps. This engine copies no stale rule. On 2026-09-25 the owner
  chose to leave steps out. Banchi numbers them by hand. `deferred/banchi-build-steps.md`
  holds the item and the trigger that brings it back. The engine refuses a tree that
  holds a pending step marker, and the refusal names that file.
- **Debts.** claim-ids.py has no debt kind. There is no rule to copy.
- **The flat-file fallback.** With no `ORDER.json`, claim-ids.py reads decisions from
  the flat `docs/DECISIONS.md`. That serves commits before the split. banchi main has
  the manifest.
- **No rename without a manifest.** claim-ids.py renames no file when `ORDER.json` is
  missing. The engine renames a claimed file whether or not a manifest exists.
- **The branch-side reads.** `--stale`, `--unclaim`, `--landed`, `--porcelain` and
  `merging()` serve a claim made on a branch before the merge. This stamp claims only
  on the default branch. `--check` refuses a number written on a branch instead.

**Deliberate differences from claim-ids.py.** Parity above is not changed by any of
them. All but the last two come up only in a state claim-ids.py gets wrong, or one
banchi's tree does not hold today. The last two come up in banchi's normal flow.

- A malformed pending heading (`## D012`, `## D-Bad_Slug`) is refused. MEASURED:
  claim-ids.py claims it as an id.
- A duplicate pending slug, or a pending file claim-ids.py's filename rule cannot find,
  is refused. claim-ids.py claims it and leaves two headings on one number, or leaves
  the file unrenamed.
- Path cites run longest slug first. MEASURED: claim-ids.py rewrote a path cite of
  `D-probe-foo-bar.md` to the id of `D-probe-foo`, because the shorter slug ran first.
- The ceiling is read off the tree being stamped, not off `--ref`. At the merge, that
  tree is main.
- A rewritten file keeps its own line ending. Python's `write_text` writes the
  platform's. On banchi today, no text file the walk opens has a CRLF.
- A rename onto a file that already exists is refused before anything is written.
  claim-ids.py's `Path.rename` replaces that file on POSIX and fails on Windows.
- A ref and HEAD with no merge base: claim-ids.py refuses, exit 2. `--stamp` reads no
  ref and never asks. `--check` off the default branch prints "NOT ASKED" and does
  not refuse.
- A failed `regenerate` stops the run and nothing is pushed. claim-ids.py's
  `settle_corpus` ignores a failed generator, and the claim still lands.
- `--check` refuses a record numbered on a branch. claim-ids.py claims on the branch,
  so its `--stale` passes a branch number that main has not taken. This one is in
  banchi's normal flow: `make merge` (`scripts/merge-pr.py`, which calls
  `scripts/claim-ids.py`) claims numbers on the branch for every pull request.
  **Adoption step:** banchi must retire the branch-side claim in `make merge` before it
  runs this action's `--check`. Until then, `--check` is red on every pull request
  `make merge` claims.

Two more shapes stay unmechanized everywhere. q_max's `docs/decisions/B*` and `G*`
folders have no pending form today. Neither do banchi's `docs/debts` folder or its `T`
prefix. There is nothing yet for a shared stamp to claim there.

## Two things the config must state, never guess

**Numbering.** q_max's own `--stamp` takes the highest existing number, per kind, and
adds one. It never fills a gap. sharables' and job-cost-reporting's own claim tools
both take the lowest number not already taken. Each fills a gap if one exists. In
practice, neither repo has ever had a gap to fill. From the outside, this looks like
one rule. It is two, read from two different pieces of source. `actions/stamp/README.md`
names both. It says to check this field. Never guess it.

**Cite rewrite.** Three repos rewrite a slug citation to a different shape. q_max
writes `D-nnn, Title`. job-cost-reporting writes `id, gloss`. sharables writes the bare
id, with no gloss at all. Its own separate citation check enforces the gloss by hand
instead. The config's `cite.template` states this per repo. Nothing here assumes that a
gloss belongs on every citation.

## The one refusal this rule protects, and where it is asked

`--check`'s branch question asks: is every pending record one HEAD itself just added?
It exists to tell apart two states q_max's own log once conflated, in its own `D-478`,
the stamp checks its own tree. One state is a pending record waiting its normal turn.
The other is a pending record whose stamp run failed, or whose push was rejected
twice. The question is asked only on the default branch, and only while something is
pending. Every other run reads no git history at all. `stamp.mjs`'s own `addedByHead`
and merge-order reader are lifted from `harness/decision-refs.mjs` nearly unchanged.
That logic was already measured against q_max's real history. Rewriting it a second
way would only add a second chance to get it wrong.

## The gap `stamp.yml` itself measured, closed here

q_max's own `stamp.yml` pushes a commit with the workflow's own token. GitHub starts no
workflow on a push made with that token. So nothing else ever checked the commit
`stamp.yml` pushed. q_max fixed this by running its own gate commands inside
`stamp.yml`, before the push. `actions/stamp/action.yml` carries the same fix as an
input, `gate-command`. Every adopting repo gets it for free.

It goes one step further. On a rejected push, q_max's own workflow rebases and pushes
again. It never re-runs the gate on the rebased tree. `actions/stamp`'s retry
re-derives the whole stamp from the fresh tree instead. It re-gates every time, up to
three attempts.

## The owner's bar: adopting this changes nothing else

q_max's own `writeBlocks`/gloss pass, sharables' `_index.md`, and job-cost-reporting's
`docs/Decision_Index.md` and `docs/Owner_Corrections.md` are all generators. Each
repo's own tool runs one right after it claims a number. This engine's job is not to
reproduce that. A repo that adopts it must not lose it either. `action.yml` takes one
more optional input, `regenerate`: a command that runs on the stamped tree, after
`--stamp`, before the gate, in the same commit. Each repo keeps its own generator.
This input only decides when it runs.

MEASURED: q_max's own `harness/decision-refs.mjs --gloss --write` already exists as a
standalone pair of flags. Running it right after `--stamp` reproduces `stamp()`'s own
tail exactly, because it calls the same two functions in the same order. No change to
q_max's tool was needed. Same for sharables (`scripts/check_records.py
--write-index`) and job-cost-reporting (its two generator scripts, run in sequence,
each redirected to its own target file). All three are named in
`actions/stamp/README.md`, and proven against each repo's own real tree.

## The mechanism

This entry adds no new CLAUDE.md rule anchor. `lint/rule_mechanisms.json` keeps
`git-slug-then-claim-number` as `unmechanized` in this repo. That matches
`actions/ste-lint`, which carries no anchor of its own either. A reusable action lives
here, but it enforces nothing until another repo's own workflow calls it. Fixtures:
`actions/stamp/test_stamp.mjs` for the engine, and `actions/stamp/test_action.sh` for
the composite action's own shell logic. Both are wired into `gates`, `gates-windows`
and `gates-macos` in `.github/workflows/gates.yml`.

## What would reopen this

banchi asks to adopt this tool. Banchi's own tool learns to claim a step in
`docs/gates/steps/` (see `deferred/banchi-build-steps.md`). A fifth repo
turns up with a shape none of the three formats covers. Either the `numbering` or the
`cite` assumption above turns out wrong for a repo nobody has read yet. Any of these is
a reason to come back to this entry before writing a fourth format into `stamp.mjs`.
None of them is a reason to guess one in.
