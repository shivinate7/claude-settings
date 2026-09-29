# actions/stamp

One shared engine for CLAUDE.md's rule `git-slug-then-claim-number`. The rule: "Never
allocate a numbered record on a branch. Write a slug. Claim the number at merge." This
folder names no repo. It states record shapes, config fields, and a contract. Each repo
reads its own tree and writes its own config.

## The contract

A repo that adopts this engine meets each item below.

1. A branch writes a record with a pending marker, never a number.
2. The repo keeps one config file in its own tree, such as `.github/stamp.json`. Every
   field in it is read off the repo's own claim tool or its own tree. No field is a guess.
3. Every pull request runs mode `check`. A record numbered on the branch fails it.
4. Every push to the default branch runs mode `stamp`. It numbers each pending record,
   runs the repo's own generator and full gate, and pushes one commit.
5. The workflow pins this action by commit SHA and holds the concurrency lock.

## Record shapes

1. **Number in frontmatter only.** `id: pending` becomes `id: D-042`. The file keeps its
   name. See `examples/frontmatter.stamp.json` and
   `examples/frontmatter-prefixed-cite.stamp.json`.
2. **Number in frontmatter and in the filename.** A file `_<slug>.md` with an empty `id:`
   becomes `D42_<slug>.md` with `id: D42`. See `examples/frontmatter-filename.stamp.json`.
3. **Number in a heading.** The config sets `"format": "heading"`. The code is its own
   module, `formats/heading.mjs`. See `examples/heading.stamp.json`. A kind has one of two
   corpus shapes.
   - `folder`: one file per record, with the heading on line 1. The file
     `D-<slug>.md` that starts `## D-<slug> — Title` becomes `D258-<slug>.md` that starts
     `## D258 — Title`.
   - `file`: one flat file, and every heading is a record. `## C-<slug> — Title` becomes
     `## C12 — Title`. The file keeps its name.

A shape that no config field can state is not covered. Bring it to the owner as a
question. Do not add a repo name here to fit it.

## Modes

```
node stamp.mjs --stamp --config <path> [--root <path>]
node stamp.mjs --check --config <path> [--root <path>] [--base <ref>]
```

`--root` defaults to the current directory. It must be the root of the checkout.

**`--stamp`** gives each pending record the next number for its kind, in the order the
config states. Then it rewrites each cite of the record's slug to the numbered form. It
never renumbers a record. It runs the structural checks of `--check` first. If one fails,
it writes nothing.

**`--check`** writes nothing. It refuses these states on every branch:

- a malformed record, which is neither pending nor numbered
- a duplicate id or a duplicate slug
- a cite that resolves to no record
- a marker that the config lists in `unclaimed`

It asks one more question, and the question depends on the branch.

- **On the default branch**, it refuses a pending record that HEAD did not add. Such a
  record means that the stamp did not run, or that its push was rejected. A record that
  HEAD added waits for its turn. It is not refused.
- **Off the default branch**, it compares this tree with the base tree. It asks the
  question for all three shapes, with the same loader that reads this tree. It refuses
  these states:
  - A record whose number in this tree is not its number in the base tree. This catches a
    new record with a number. It also catches a record that was pending on the base and
    has a number now.
  - A renamed record. The base holds the same number under another key. The message says
    that the record was renamed, and it names the old key and the new key. The fix is to
    restore the old key.
  - A removed record. A number is removed when the base tree holds it and no record of this
    tree holds it, for the same kind. Numbers are permanent. A branch may delete a record
    only when the kind's `RETIRED` list names its number (see "The retired-numbers list").
  - A number removed from a `RETIRED` list. The list is append-only.

A pull request checkout is always off the default branch. The engine knows it is one when
`GITHUB_BASE_REF` is set, or when `GITHUB_REF` starts with `refs/pull/`.

The base ref is the first of these that is set: `--base <ref>`,
`origin/$GITHUB_BASE_REF`, or `origin/<defaultBranch>`. The base tree is the merge base of
HEAD and that ref. The tip of the ref is not used. The tip can hold the same number for a
different record, and then the defect does not show.

**A base that cannot be read is never a pass.** These states make the base unreadable. The
ref is missing, or it has no merge base with HEAD. The config has no `defaultBranch` and no
`--base` is given. The tree has no git. The result then depends on where the check runs:

- **In GitHub Actions** (`GITHUB_ACTIONS` is `true`), `--check` exits 1. The message says that
  the read could not run, and it names the remedy.
- **Everywhere else**, `--check` prints a line that starts with `UNKNOWN:` and names the same
  remedy. It exits 0. It does not print the line that says the records are in order.

The remedy is to fetch the base branch with its history, or to pass `--base <ref>`. A check
job needs `actions/checkout` with `fetch-depth: 0`. A shallow fetch of the base is not
enough, because git must find the merge base of HEAD and the base ref.

**Record identity across the two trees.** A frontmatter record is the same record when it
has the same kind and slug. Its key is the slug. A `folder` heading record is the same
record when it has the same file. Its key is the file path. A `file` heading record has no
key but its number. So a branch that renames a numbered `folder` heading file is refused
too. So is a branch that changes the slug of a numbered frontmatter record. A rename of a
frontmatter file with the same slug passes. An edit to a title passes in every shape.

**A same-number swap.** A branch can delete a `file` heading record and write a different
record with the same number. That is now the same as an edit in place, because the removal
refusal catches each number that no record holds. The engine does not compare titles or
content.

## The retired-numbers list

A kind may keep a file named `RETIRED` in its `folder`. It has no extension, so the
`filePattern` never reads it as a record. Write one line for each retired number. A line
starts with the id, as the kind renders it (`D-012`, or `D12`). It may then hold the last
title, after a space. The engine skips a blank line. It refuses any other line that does not
start with an id.

```
D-012 A decision that no longer governs
D-013
```

The rules:

- A branch may delete a numbered record when the same tree's list names its number.
- The list is append-only. A number the base list names must stay in this list.
- The allocator counts a listed number as taken, in both `max_plus_one` and `lowest_free`.
  So a deleted top number is never given out again.
- A number that is in the list and still held by a record is refused. Remove one of them.

The heading format (`"format": "heading"`) does not read the list. A removal in that format
stays refused, and the message says so.

## The config file

The config is JSON. `loadConfig` rejects a missing required field before it reads the
tree. A default applies when a field is not set.

### Top-level fields

| Field | Shapes | Meaning |
|---|---|---|
| `format` | all | Not set for shapes 1 and 2. `"heading"` for shape 3. |
| `defaultBranch` | all | The default branch name. `--check` needs it to find the branch. Without it, `--check` needs `--base` or `GITHUB_BASE_REF`. |
| `kinds` | all | A list of record kinds. It must not be empty. |
| `cite` | all | How a cite of a slug is found and rewritten. Omit it for shapes 1 and 2 if the repo cites by path. |
| `slugRegex` | 3 | The slug grammar. A pending token is `<prefix>-<slug>` and nothing else. |
| `walk` | 3 | Which files the cite rewrite opens. |
| `unclaimed` | 3 | Markers the engine refuses and never numbers. |

### Kind fields, shapes 1 and 2

| Field | Default | Meaning |
|---|---|---|
| `id` | required | A label for log lines and record keys. It is not read from a file. |
| `folder` | required | The folder that holds the records. Only files directly in it are read. |
| `filePattern` | `*.md` | Which files in `folder` are records. |
| `excludeFiles` | `[]` | Globs of files in `folder` that are not records, such as an index. |
| `prefix` | required | The id prefix, such as `D`. |
| `pad` | `0` | The number width. With `pad: 3`, `{prefix}-{n}` renders `D-042`. |
| `idTemplate` | required | How an id is written and read back. It uses `{prefix}` and `{n}`. |
| `pendingRegex` | required | The frontmatter line that marks a pending record. |
| `location` | `frontmatter` | `frontmatter` or `frontmatter+filename`. |
| `filenamePendingPrefix` | `_` | Shape 2. The filename marker of a pending record. Shape 2 reads the pending state from the filename only. |
| `filenameTemplate` | required for shape 2 | The numbered filename. `{rest}` is the pending name without its marker. |
| `order` | `date` | The claim order: `date`, `merge` (the order of first-parent adds in git), or `filename`. |
| `numbering` | `max_plus_one` | `max_plus_one` never fills a gap. `lowest_free` fills the lowest gap first. |
| `allowRanges` | `false` | Set it when an id can hold more than one number, such as `D-044 to D-046`. The engine counts each number. It never writes a range. |
| `slugField` | `slug` | The frontmatter field that holds the slug. |
| `dateField` | `date` | The frontmatter field that `order: "date"` reads. |
| `glossField` | `title` | The frontmatter field that `{gloss}` renders. |
| `requireFieldsOnPending` | `[]` | A pending record without one of these fields is malformed. |

### Cite fields, shapes 1 and 2

| Field | Default | Meaning |
|---|---|---|
| `pattern` | required | A regex for the full span that the rewrite replaces. Write it for that span only. Text around it stays. |
| `slugGroup` | `1` | The capture group that holds the slug. |
| `prefixGroup` | not set | The capture group that holds the prefix, for a cite that names its kind, such as `D‹slug›`. A cite whose prefix does not match its record stays as text. |
| `template` | required | The numbered form. It uses `{id}`, `{gloss}`, and `{title}`. |
| `scanGlobs` | `["**/*.md"]` | The files the rewrite and the dangling-cite check read. |
| `excludeGlobs` | `[]` | Files that neither reads. |

The dangling-cite check skips frontmatter, fenced blocks, code spans, and link targets. A
file that teaches the cite syntax in plain text needs an `excludeGlobs` entry. Find each
entry from a refusal of `--check` on your own tree. Do not guess the list.

### Kind fields, shape 3

| Field | Default | Meaning |
|---|---|---|
| `id` | required | A label for log lines and record keys. |
| `prefix` | required | The id prefix. |
| `folder` or `file` | one required | `folder` for one file per record. `file` for one flat file. Never both. |
| `pendingRegex` | required | The heading that may hold a pending id. Group 1 is the token. A token that is not a number and not `-<slug>` is malformed. |
| `numberedRegex` | required | Each numbered heading. Group 1 is the number. The next id is the highest match plus one. |
| `idTemplate` | required | The heading and cite form of an id. |
| `pad` | `0` | The number width in the id. |
| `filenameTemplate` | required for `folder` | The numbered filename. It uses `{prefix}`, `{n}`, and `{rest}`. |
| `filenamePad` | `0` | The number width in the filename. |
| `manifest` | not set | A JSON file that lists the folder's filenames in order. A listed pending name is renamed in place. Nothing is appended. |
| `manifestKey` | `order` | The key of the list in the manifest. |
| `manifestAscii` | `true` | `true` writes the manifest as Python's `json.dumps(indent=2)` does, with each non-ASCII character escaped. `false` writes plain UTF-8. |
| `pathCite` | not set | A regex for a path cite of a pending file. `{token}` is the slug. The match becomes the bare id. |
| `numbering` | `max_plus_one` | Shape 3 accepts `max_plus_one` only. |

A `folder` record's file is found by its slug. The first name in corpus order that is
`<slug>.md` or starts with `<slug>-` is the file. The numbered name keeps only the text
after `<slug>-`.

### Cite, walk, and unclaimed fields, shape 3

| Field | Default | Meaning |
|---|---|---|
| `cite.before`, `cite.after` | `(?<![-\p{L}\p{N}_])`, `(?![-\p{L}\p{N}_])` | The boundary around a slug token. Write Python's Unicode `\w` as `[\p{L}\p{N}_]`. |
| `walk.textSuffixes` | required | The file suffixes the rewrite opens. |
| `walk.skipDirs` | `[]` | Folder names the walk does not enter. |
| `walk.skipDotDirs` | `true` | The walk does not enter a folder whose name starts with a dot. |
| `walk.extensionlessDirs` | `[]` | Folders whose files without a suffix the walk opens too. |
| `unclaimed[].folder` | required | The folder whose `.md` files are read. |
| `unclaimed[].pattern` | required | A regex with the flags `gmu` and a named group `(?<slug>...)`. |
| `unclaimed[].message` | required | The text of the refusal. |
| `unclaimed[].label` | not set | When set, the refusal names `<label> <slug>`, not the matched line. |

The walk never follows a symlink. Use `unclaimed` for a marker that your repo has no claim
rule for yet. Both modes refuse it before they write anything.

## The composite action

```yaml
uses: shivinate7/claude-settings/actions/stamp@<sha>
```

**Pin it by commit SHA. Never use `@main`.** Mode `stamp` writes to your default branch.

### Inputs

| Input | Default | Meaning |
|---|---|---|
| `mode` | `stamp` | `stamp` or `check`. |
| `config` | required | The config path, from the repository root. |
| `base` | empty | Mode `check` only. The base ref, passed to `stamp.mjs` as `--base`, and only when it is set. When it is empty, the engine picks the base itself. |
| `gate-command` | empty | Mode `stamp` only, and required there. Your own full check. It must pass on the stamped tree before the push. |
| `regenerate` | empty | Mode `stamp` only. Your own generator. It runs after `--stamp` and before the gate, in the same commit. |
| `commit-subject` | `Stamp {ids}` | The commit subject. `{ids}` becomes the ids that the run stamped. |
| `token` | empty | Mode `stamp` only, and required there. The push token. Only `git fetch` and `git push` receive it. |
| `bot-name` | `record-stamp[bot]` | The commit author name. |
| `bot-email` | `record-stamp@users.noreply.github.com` | The commit author email. |

**Mode `check`** runs `stamp.mjs --check --config <config>` and nothing else. When `base` is
set, it adds `--base <base>`. It needs no default branch, no gate, no commit, and no push.
It works with `contents: read`. Its checkout needs `fetch-depth: 0`. A shallow fetch of the
base is not enough.

**Mode `stamp`** refuses to run off the default branch. It refuses an empty
`gate-command`. It stamps, runs `regenerate`, runs the gate, commits, and pushes. When
nothing is pending, it stops before `regenerate`. When the push is rejected, it starts
again from the new tree and runs the gate again, up to 3 times. It never rebases a commit
that the gate already passed, because a rebased tree is a tree that no gate read.

**The token.** The checkout must set `persist-credentials: false`. Mode `stamp` refuses to
run when `.git/config` holds a credential for the remote, and when `token` is empty. The
action copies the token out of its environment at start. It gives the token to `git fetch`
and `git push` only, in per-command env. Your `regenerate` and `gate-command` do not inherit
it. Limit: the gate runs as the same user, so a determined attacker could still read process
memory. Full isolation needs a separate push job.

**The concurrency rule.** A composite action cannot hold a lock. The job that runs mode
`stamp` must set `concurrency: {group: <name>, cancel-in-progress: false}`. Two runs at
the same time could otherwise claim the same number.

```yaml
name: records
on:
  pull_request:
  push:
    branches: [main]
jobs:
  check:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        with:
          fetch-depth: 0   # the base tree and the merge base
      - uses: shivinate7/claude-settings/actions/stamp@<sha>
        with:
          mode: check
          config: .github/stamp.json
  stamp:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    concurrency:
      group: stamp-main
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        with:
          fetch-depth: 0   # order "merge", and the default-branch question
          persist-credentials: false
      - uses: shivinate7/claude-settings/actions/stamp@<sha>
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          config: .github/stamp.json
          regenerate: "<your own generator>"
          gate-command: "<your own full check>"
```

## Adoption checklist

Do each step in your own repo, from your own tree.

1. Pick the shape that your records have. Start from the example with that shape.
2. Measure each field from your own claim tool. Read `numbering`, `order`, the pending
   marker, the id form, and the cite form from its source. Do not copy a value from an
   example.
3. Set `regenerate` to run your own generators, such as an index or a manifest append.
   Adoption must change nothing else in the tree.
4. Set `gate-command` to your own full check, the same one your pull requests run.
5. Run `--stamp` on a copy of your tree. Compare the result with your own claim tool's
   result on a second copy. Each difference is a field to fix, or a question for the
   owner.
6. Run `--check` on your tree. Read each refusal. Add an `excludeGlobs` entry only for a
   file that teaches the cite syntax.
7. Retire each step that claims a number on a branch, such as a claim in a merge script.
   Mode `check` refuses each number that a branch writes.
8. Make each local check that refuses a pending record on the default branch accept a
   record that HEAD itself added. The stamp run for that commit has not had its turn yet.
9. Add both jobs to your workflow. Pin the SHA. Set the concurrency lock.

## Tests

```
node actions/stamp/test_stamp.mjs   # the engine: numbering, rename, cite rewrite, --check
bash actions/stamp/test_action.sh   # run.sh, both modes, against a real git remote
```

Both build their own temporary folders. Neither reads or writes this repository's own
tree. Both run in `gates`, `gates-windows`, and `gates-macos` in
`.github/workflows/gates.yml`.
