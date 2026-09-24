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
- banchi: the number lives in the filename AND the heading, in a per-file corpus.
  MEASURED on `main`, 2026-09-24: `docs/decisions/D-<slug>.md` becomes
  `docs/decisions/D001-<slug>.md` (261 files, 3-digit filename pad, `## D1 —` in the
  heading, no pad there), tracked by `docs/decisions/ORDER.json`. `docs/debts/` (34
  files) and `docs/gates/steps/` (25 files) carry their own `ORDER.json` the same way.
  Flat files `docs/DECISIONS.md`, `docs/DEBTS.md`, `docs/CODES-DECISIONS.md` sit
  beside them; `scripts/split-debts.py` and `scripts/debts_corpus.py` suggest these are
  generated or legacy rather than the source of truth. Its own claim tool,
  `scripts/claim-ids.py`, is 1727 lines.

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

`actions/stamp/stamp.mjs` covers two shapes:

1. Number in frontmatter only (q_max, sharables).
2. Number in frontmatter and in the filename (job-cost-reporting).

Banchi's shape is not built in this PR. It is deferred to a follow-up lane, not
skipped for a shape mismatch. The number lives in both the filename and the heading,
a third location neither shape above covers. Its own claim tool is 1727 lines.

That lane must handle three things. A filename-plus-heading number: the filename
pads to 3 digits, the heading does not. `ORDER.json`, one per corpus
(`docs/decisions/ORDER.json`, `docs/debts/ORDER.json`, `docs/gates/ORDER.json`), read
and written alongside the rename. And the flat files (`docs/DECISIONS.md`,
`docs/DEBTS.md`, `docs/CODES-DECISIONS.md`). These may turn out to need only a
`regenerate` job calling banchi's own scripts, not a fourth shape this engine must
reproduce.

A repo shaped like banchi keeps its own claim tool until that lane runs. That lane
reads `scripts/claim-ids.py` and `main` in full. The partial read this entry first
drew on described an older, flat-file-only design. That design no longer matches the
corpus banchi runs today.

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

A repo shaped like banchi asks to adopt this tool. A fifth repo turns up with a sixth
shape neither format here, nor banchi's own, covers. Either the `numbering` or the
`cite` assumption above turns out wrong for a repo nobody has read yet. Any of these is
a reason to come back to this entry before writing a third format into `stamp.mjs`.
None of them is a reason to guess one in.
