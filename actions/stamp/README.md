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
4. Every push to the default branch runs mode `check` too. A pending record there fails it.
5. The claim runs before the merge, through the merge tool ("The merge tool contract" below).
6. The workflow pins this action by commit SHA.

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
     `## D258 — Title`. A debt is a `folder` kind whose `filenameTemplate` has no
     `{prefix}`: `DEBT-<slug>.md` starting `## DEBT-<slug> — Title` becomes `079-<slug>.md`
     starting `## DEBT79 — Title`. Its `numberedRegex` may accept a bare `## 12` too.
   - `file`: one flat file, and every heading is a record. `## C-<slug> — Title` becomes
     `## C12 — Title`. The file keeps its name.

A shape that no config field can state is not covered. Bring it to the owner as a
question. Do not add a repo name here to fit it.

## Modes

```
node stamp.mjs --claim --base <ref> --config <path> [--root <path>]
node stamp.mjs --check --config <path> [--root <path>] [--base <ref>]
```

`--root` defaults to the current directory. It must be the root of the checkout.

**`--claim`** gives each pending record the next number for its kind, in the order the
config states. Then it rewrites each cite of the record's slug to the numbered form. It
never renumbers a record. It runs the structural checks of `--check` first. If one fails, it
writes nothing. It runs on a branch, before the merge. It needs `--base`. The next
number is above every number in this tree, in the tip of `--base`, and in every commit of the
history of `--base`. It is also above each `RETIRED` list of both. So a number that the base
took since the cut, or that a record once held and lost, is never reused. A base that git
cannot read stops the run before it writes. So does a shallow clone, or a history git cannot
read: a cut-short history could hand out a low number. The message names the fix, which is
to fetch full history (`fetch-depth: 0`). When it claimed something, it runs
the config's `regenerate` command, and its last line is `Record-claim: <ids>`. The caller
puts that line in the claim commit as a trailer.

**`--check`** writes nothing. It refuses these states on every branch:

- a malformed record, which is neither pending nor numbered
- a duplicate id or a duplicate slug
- a cite that resolves to no record
- a marker that the config lists in `unclaimed`

It asks one more question, and the question depends on the branch.

- **On the default branch**, it refuses any pending record, HEAD's own included. The
  claim runs before the merge, so a pending record there was never claimed.
- **Off the default branch**, it compares this tree with the base tree. It asks the
  question for all three shapes, with the same loader that reads this tree. It refuses
  these states:
  - A record whose number in this tree is not its number in the base tree. This catches a
    new record with a number. It also catches a record that was pending on the base and
    has a number now.
  - A renamed record. The base holds the same number under another key. The message says
    that the record was renamed, and it names the old key and the new key. The fix is to
    restore the old key.
  - A number removed from a `RETIRED` list. The list is append-only.

  One exception to the first state. A number that a commit with a `Record-claim: <ids>`
  trailer added is accepted when the base ref, tip and history, never held it. The same commit
  must add the number itself: its parent lacks the number, and it holds the number. A later
  edit of a number that another commit wrote is not vouched for. A number with no trailer stays refused. A number that the
  base ref took after the claim, or held before it, is refused, and the fix is to claim again.

  A flat-file entry keys by its number and heading title. A title change under one number is
  refused as a rename: delete the entry and claim a new number.

  A record may be deleted. The check does not refuse a removed record. Its number stays
  taken, because the claim reads the highest number ever used from the history of the base
  ref. A kind that keeps a `RETIRED` list works as before (see "The retired-numbers list").
  Known gap: after a kind's folder or file is moved, numbers used under the old path are not
  seen. Keep the old path in the kind's config, or check those numbers by hand.

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
  A caller that runs `--check` outside Actions, such as the merge tool, must read an
  `UNKNOWN:` line as a failure. The exit code 0 does not mean a pass.

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

- The list is optional. A branch may delete a numbered record with or without it.
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
| `regenerate` | all | Your own generator, a shell command. `--claim` runs it after the claim. |
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
| `cite.glossFirstUse` | `[]` | Globs of files. In each, a claimed cite of a `folder` record gains ` (gloss)` at its first use in a paragraph. The gloss is the first six words of the record title, with `(`, `)` and backticks dropped. A blank line or a bullet starts a paragraph. A cite already followed by ` (` or `, word` is left alone. A heading line is skipped. A `file` record has no gloss. The gloss boundary is fixed, and it ignores `cite.before` and `cite.after`. |
| `walk.textSuffixes` | required | The file suffixes the rewrite opens. |
| `walk.skipDirs` | `[]` | Folder names the walk does not enter. |
| `walk.skipDotDirs` | `true` | The walk does not enter a folder whose name starts with a dot. |
| `walk.extensionlessDirs` | `[]` | Folders whose files without a suffix the walk opens too. |
| `unclaimed[].folder` | required | The folder whose `.md` files are read. |
| `unclaimed[].pattern` | required | A regex with the flags `gmu` and a named group `(?<slug>...)`. |
| `unclaimed[].message` | required | The text of the refusal. |
| `unclaimed[].label` | not set | When set, the refusal names `<label> <slug>`, not the matched line. |

The walk never follows a symlink. Use `unclaimed` for a marker that your repo has no claim
rule for yet. `--claim` and `--check` refuse it before they write anything.

## The composite action

```yaml
uses: shivinate7/claude-settings/actions/stamp@<sha>
```

**Pin it by commit SHA. Never use `@main`.**

### Inputs

| Input | Default | Meaning |
|---|---|---|
| `mode` | `check` | `check`, the only mode. Any other value is refused. |
| `config` | required | The config path, from the repository root. |
| `base` | empty | The base ref, passed to `stamp.mjs` as `--base`, and only when it is set. When it is empty, the engine picks the base itself. |

**Mode `check`** runs `stamp.mjs --check --config <config>` and nothing else. When `base` is
set, it adds `--base <base>`. It needs no default branch, no gate, no commit, and no push.
It works with `contents: read`. Its checkout needs `fetch-depth: 0`. A shallow fetch of the
base is not enough.

```yaml
name: records
on:
  pull_request:
  push:
    branches: [main]
jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        with:
          fetch-depth: 0   # the base tree, the merge base, and the default-branch question
      - uses: shivinate7/claude-settings/actions/stamp@<sha>
        with:
          mode: check
          config: .github/stamp.json
```

## Adoption checklist

Do each step in your own repo, from your own tree.

1. Pick the shape that your records have. Start from the example with that shape.
2. Measure each field from your own claim tool. Read `numbering`, `order`, the pending
   marker, the id form, and the cite form from its source. Do not copy a value from an
   example.
3. Set `regenerate` to run your own generators, such as an index or a manifest append.
   Adoption must change nothing else in the tree.
4. Run `--claim --base <ref>` on a copy of your tree. Compare the result with your own claim
   tool's result on a second copy. Each difference is a field to fix, or a question for
   the owner.
5. Run `--check` on your tree. Read each refusal. Add an `excludeGlobs` entry only for a
   file that teaches the cite syntax.
6. Retire each step that claims a number on a branch, such as a claim in a merge script.
   Mode `check` refuses each number that a branch writes.
7. Add the check job to your workflow. Pin the SHA. Run it on every pull request and on every
   push to the default branch. `--check` on the default branch refuses any pending record.

## The merge tool contract

The command `merge` (`merge/merge.py`, see the claude-settings README) claims before the
merge, on the pull request branch. Main never holds a pending record. A repo that moves to it
meets each item below.

1. One config file holds everything. It is the stamp config the repo already has, or a new
   `.github/stamp.json`. The command reads it from the repo root. A different path goes in
   `--config`.
2. `defaultBranch` is set. The command refuses a config without it.
3. A `merge` block sets `method` (`merge`, `squash` or `rebase`) and `deadlineMinutes`. The
   command refuses a config that lacks either, but only under `--confirm`. A preview does
   not check them. It never guesses them. Read `method` from
   the repo's own merge history.
4. `merge.requiredChecks` is `"protection"` (the default) or a list of check names.
   `"protection"` reads the branch protection of the pull request's base. If the list is
   empty or cannot be read, the command stops before the claim push. A repo with no branch
   protection on a base, such as an integration branch, must write the list.
5. `merge.afterMerge` is a list of shell commands. Each runs with `bash -c` in the repo root,
   after the local base branch moves. `merge.deleteBranch` is a boolean.
6. Every pull request runs mode `check`, with `fetch-depth: 0`. A number that a
   `Record-claim` commit added is accepted. Any other number a branch adds is refused.
7. Every push to the default branch runs mode `check` too. It refuses any pending record
   there, and needs only `contents: read`.
8. A check name can repeat, such as one job in two workflows. The wait keeps every entry
   of a name. All of them must pass, and one red entry stops the wait.

The tool keeps these behaviours. The adopting repo needs no setting for them.

- It claims only for a pull request into the default branch. For any other base, records
  stay `id: pending` until that base merges into the default branch.
- It takes a lock, the ref `refs/merge-lock/<base>` on origin, for the pull request's base. The lock expires
  after `deadlineMinutes` plus ten minutes.
- It claims in a temporary worktree at the pull request head. It pushes the claim as a
  plain push, never a force push.
- The wait stops on any failed or cancelled check, required or not. This holds
  for each entry of a duplicate check name. A DIRTY branch or a moved head stops it too.
- A head that still reads as the pre-claim SHA is waited on until the deadline.
- On a stop, it reverts the claim, only while the origin head is the claim commit.
- It merges with `--match-head-commit`. It never passes `--admin`.

## Adoption checklist, the merge tool

Do each step in your own repo, from your own tree.

1. Do steps 1 to 5 of the engine checklist above, so the config reads your tree correctly.
2. Add the `merge` block. Read `method` from the repo's merge history. Set
   `deadlineMinutes` to a bit more than your slowest required check.
3. Set `requiredChecks`. For a branch with protection, use `"protection"`. Otherwise name the
   checks in a list.
4. Add each command that must run after the merge to `afterMerge`, such as a sync of a
   primary checkout. Each exits 0 on a run with nothing to do.
5. Set `regenerate` in the config, not in the workflow input. The claim runs it in the
   same commit.
6. Switch the workflow. Run mode `check` on every pull request, and on every push to the
   default branch, with `contents: read`.
7. Retire your own claim step, such as a claim in a merge script. Keep a wrapper that
   passes its arguments through and adds nothing. Remove any other.
8. Run `merge <pr>` with no flag on a real pull request. Read the preview. Then run one real
   merge with `--confirm`.
9. Check that the default branch holds no pending record after the merge.

## Tests

```
node actions/stamp/test_stamp.mjs   # the engine: numbering, rename, cite rewrite, --check
bash actions/stamp/test_action.sh   # run.sh, mode check, against a real git remote
```

Both build their own temporary folders. Neither reads or writes this repository's own
tree. Both run in `gates`, `gates-windows`, and `gates-macos` in
`.github/workflows/gates.yml`.
