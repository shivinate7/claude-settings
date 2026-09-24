# actions/stamp

One shared parser for CLAUDE.md's rule `git-slug-then-claim-number`. The rule: "Never
allocate a numbered record on a branch. Write a slug. Claim the number at merge." See
`decisions/one-shared-record-stamp.md` for why this is one tool with a config file per
repo. No repo gets its own record shape rewritten.

Pin it by commit SHA. Never use `@main`. This action writes to your default branch.

```yaml
uses: shivinate7/claude-settings/actions/stamp@<sha>
```

## What it does

A branch writes a record with a pending marker instead of a number. Some repos use `id:
pending`. Others leave `id:` empty. `--stamp` gives every pending record the next number
for its kind, in the order your config states. It then rewrites every cite of that
record's slug to the numbered form. `--check` refuses a record numbered on a branch. It
also refuses a malformed record, a duplicate id, and a cite that resolves to nothing. It
writes nothing either way.

## Formats covered

1. **Number in frontmatter only.** `id: pending` becomes `id: D-042`. This covers q_max's
   `docs/decisions` folder. It also covers sharables' `decisions`, `findings` and `gaps`
   folders.
2. **Number in frontmatter and in the filename.** A file named `_<slug>.md`, with an
   empty `id:`, becomes `D42_<slug>.md` with `id: D42`. This covers
   job-cost-reporting's `docs/decisions`, `docs/build`, `docs/findings` and
   `docs/questions` folders.

3. **Number in a heading, and for a split corpus in the filename too.** This is
   banchi's shape, read off its own `scripts/claim-ids.py`. A file
   `docs/decisions/D-<slug>.md` whose first line is `## D-<slug> — Title` becomes
   `docs/decisions/D258-<slug>.md` with `## D258 — Title`. The filename pads to 3 digits.
   The heading does not. A heading `## C-<slug> — Title` inside the flat
   `docs/CODES-DECISIONS.md` becomes `## C12 — Title`, with no rename. The config sets
   `"format": "heading"`. The code is its own module, `formats/heading.mjs`.
   `examples/banchi.stamp.json` holds banchi's config.

**Format 3 leaves these out.** Each is named in `decisions/one-shared-record-stamp.md`.

- Build steps. claim-ids.py reads a pending step only from `docs/GATES.md`, which is
  now a pointer file. It cannot see a step in `docs/gates/steps/`. The owner picks
  what the engine does here.
- Debts. claim-ids.py has no debt kind, so there is no rule to copy.
- claim-ids.py's branch-side reads: `--stale`, `--unclaim`, `--landed` and
  `--porcelain`. A stamp that claims only on the default branch does not need them.
  `--check` refuses a number written on a branch instead.
- The ORDER.json append and the CLAUDE.md index. banchi's own
  `scripts/index-decisions.py` writes both. It runs as the `regenerate` input.

Any repo not shaped like one of these three keeps its own claim tool for now.

## The config file

A JSON file the calling repo owns and keeps in its own tree, such as
`.github/stamp.json`. Nothing here is inferred from your repo. You read every field below
off your own tool or your own tree. CLAUDE.md's rule is clear: never guess an answer the
code should give you.

```jsonc
{
  "defaultBranch": "main",       // required for --check's branch question; --stamp does not need it
  "kinds": [
    {
      "id": "decision",          // a label for log lines; not read from your files
      "folder": "docs/decisions",
      "prefix": "D",
      "pad": 3,                  // 0 (default) = no padding. "D-{n}" with pad 3 renders "D-042"
      "idTemplate": "{prefix}-{n}",     // how a numbered id is RENDERED, and how one is READ back
      "pendingRegex": "^id:[ \\t]*pending[ \\t]*$",  // the frontmatter LINE that marks a pending record
      "location": "frontmatter",        // "frontmatter" (default) | "frontmatter+filename"
      "filenamePendingPrefix": "_",     // frontmatter+filename only: the pending filename's marker
      "filenameTemplate": "{prefix}{n}_{rest}.md",  // frontmatter+filename only
      "order": "date",           // "date" (default) | "merge" (git first-parent add order) | "filename"
      "numbering": "max_plus_one", // (default) | "lowest_free" — read this off your OWN tool, do not guess
      "allowRanges": false,      // true if an id can name more than one number ("D-044 to D-046")
      "slugField": "slug",       // default "slug"
      "dateField": "date",       // default "date"; only read when order is "date"
      "glossField": "title",     // default "title"; a frontmatter field, or "title"
      "requireFieldsOnPending": []  // a pending record missing one of these is malformed
    }
  ],
  "cite": {                      // omit entirely if your repo cites by path, not by slug
    "pattern": "\\[\\[([a-z0-9][a-z0-9-]*)\\]\\]",  // the WHOLE span to replace — see note below
    "slugGroup": 1,               // which capture group holds the slug
    "prefixGroup": null,          // set this if the citation also names its own kind's prefix
    "template": "{id}, {title}",  // {id} {gloss} {title}
    "scanGlobs": ["**/*.md"],
    "excludeGlobs": [".claude/skills/**"]
  }
}
```

Four real configs sit in `examples/`. Each was read off a real repo's own tool:
`qmax.stamp.json`, `sharables.stamp.json`, `jcr.stamp.json`, `banchi.stamp.json`. Start
from whichever is closest to your own repo's shape.

**Format 3 has its own fields.** Read `examples/banchi.stamp.json` beside this list.

- `slugRegex`: the slug grammar. A pending token must be `<prefix>-<slug>` exactly.
- Per kind, `folder` (one file per record, heading on the first line) or `file` (one
  flat file, every heading is a record). Never both.
- `pendingRegex`: the heading line that may hold a pending id. Group 1 is the token. A
  token that is neither a clean number nor `-<slug>` is refused as malformed.
- `numberedRegex`: every numbered heading. Group 1 is the number. The next id is the
  highest match plus one, over every line of every file of the kind. A gap is never
  reused.
- `idTemplate` and `pad`: the heading and cite form. `filenameTemplate` and
  `filenamePad`: the filename form, for a `folder` kind only.
- `manifest` and `manifestKey`: a JSON list of filenames. A listed pending name is
  renamed in place. Nothing is appended here. Use `regenerate` for that.
- `pathCite`: a path cite of a pending file, rewritten to the bare id. `{token}` is the
  slug.
- `cite.before` and `cite.after`: the boundary around a slug token. banchi's is
  `(?<![-\w])` and `(?![-\w])`, with Python's Unicode `\w` written as
  `[\p{L}\p{N}_]`.
- `walk`: which files a cite rewrite opens. `textSuffixes`, `skipDirs` (matched by
  directory name), `skipDotDirs`, and `extensionlessDirs`. Symlinks are never walked.

**Read `numbering` off your own tool. Never guess this field.** q_max's own `--stamp`
takes the highest existing number, per kind, and adds one. It never fills a gap.
sharables' and job-cost-reporting's own claim tools both take the lowest number not
already taken. Each would fill a gap if one existed, though neither repo has ever had
one. Guessing this field from "always max plus one" would silently change a live repo's
numbering rule.

**`cite.pattern` is the span the rewrite replaces. It is not a wider match to trim
from.** sharables' own regex also matches an optional decorative backtick around the
citation. Its rewrite only ever substitutes the inner `D‹slug›`, leaving any backtick in
place. Write `pattern` to cover only that inner span. The parts around it stay in the
text either way.

**`cite.prefixGroup`** applies when a citation names its own kind's prefix beside the
slug, the way sharables writes `D‹slug›` beside `F‹slug›`. It makes the rewrite refuse a
citation whose prefix does not match the record the slug actually belongs to. This is the
same refusal sharables' own code makes on a mismatched pair.

**`cite.excludeGlobs` must name every file that teaches the citation syntax by
example.** A file that explains `[[slug]]` in prose needs to write that literal text
somewhere. `--check`'s dangling-cite refusal cannot tell that example apart from a
real cite. It can tell only when the example sits inside a backtick span, a fenced
block, or a markdown link. job-cost-reporting's own `docs/Records_Model.md`, and one
of its `docs/history/*.csv` files, both write the literal string outside all three
forms. Both needed an `excludeGlobs` entry, found by running `--check` against the
real tree and reading each refusal. Never guess this list. Read it off a refusal.

## Modes

```
node stamp.mjs --stamp --config <path> [--root <path>]
node stamp.mjs --check --config <path> [--root <path>]
```

`--root` defaults to the current directory. Both refuse and write nothing when the tree
has a structural problem. `--stamp` runs the same validation `--check` does, first.
`--check` asks one more question, and only on the default branch: is every pending record
one HEAD itself just added? An older one means that the stamp did not run, or that a push
was rejected. See `decisions/one-shared-record-stamp.md` for why that question is scoped
this way.

## The composite action

`action.yml` wraps `stamp.mjs --stamp` with the caller's own gate command, a commit, and
a push, with up to 3 retries. It refuses to run off the default branch. On a rejected
push it re-derives from the fresh tree and re-runs the gate. It never rebases the old,
already-gated commit. A rebase there is the hole q_max's own `stamp.yml` left open once:
D-478 in that log names a rebased tree that nothing ever checked.

```yaml
name: stamp
on:
  push:
    branches: [main]
permissions:
  contents: write
concurrency:
  group: stamp-main       # a composite action cannot hold this lock; your workflow must
  cancel-in-progress: false
jobs:
  stamp:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # needed for order: "merge", and for --check's branch question
      - uses: shivinate7/claude-settings/actions/stamp@<sha>
        with:
          config: .github/stamp.json
          regenerate: "node harness/decision-refs.mjs --gloss --write"
          gate-command: "npm test && npm run lint"
```

**`regenerate`** is optional. It runs after `--stamp`, before the gate, in the same
commit. A repo's own generator (a refs block, an index table, a lookup file) keeps
running. Adopting this action must change nothing else about the tree. Skipped when
nothing was pending. Read off each repo's own tool:

- q_max: `node harness/decision-refs.mjs --gloss --write`. This already exists as a
  standalone pair of flags, and reproduces `stamp()`'s own tail exactly — same two
  functions, same order. No change to q_max's tool needed.
- sharables: `python3 scripts/check_records.py --write-index`.
- job-cost-reporting: `python3 toolchain/build_decision_index.py >
  docs/Decision_Index.md && python3 harness/owner_corrections.py >
  docs/Owner_Corrections.md`.
- banchi: `python3 scripts/index-decisions.py --write`. It appends each new entry to
  `docs/decisions/ORDER.json` and regenerates the decision index in `CLAUDE.md`. The
  same string sits in `examples/banchi.stamp.json` as `"regenerate"`. `stamp.mjs` does
  not read that field. It is there so the config and the workflow input stay together.

`run.sh` holds the action's own logic. It sits in its own file so it can run and be
tested directly. `test_action.sh` does exactly that, against a throwaway git remote,
rather than only ever running inside a real Actions runner.

## Tests

```
node actions/stamp/test_stamp.mjs   # the engine: numbering, rename, cite rewrite, --check
bash actions/stamp/test_action.sh   # the action's own shell logic, against a real git remote
```

Both are plain and assert-based. Both build their own throwaway directories. Neither
reads or writes this repository's own tree. Both are wired into `gates`,
`gates-windows` and `gates-macos` in `.github/workflows/gates.yml`.
