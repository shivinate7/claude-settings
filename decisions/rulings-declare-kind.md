# Each ruling declares its kind

A decision record that a pull request adds or changes must say what kind each ruling is: a
build task, or a process change. A lint checks this on every such record. Two routes carry the
check to the owner's other repos.

## The question

How do we stop a ruling from ending in a record and never becoming work?

## The incident

A ruling in redesign.md, in another repo, never became a phone build task. The owner decided
it. The record held it. No build plan named it. The phone build never did it. Nothing failed,
because nothing linked the ruling to a plan.

Records folders differ by repo. q_max keeps its records in `docs/decisions/`, so a check that
reads only `decisions/` passes there with nothing checked (found by the oversight session's
Code-prose lane). Precedent: D-683, a Plan slug that is not a heading in `src/index.css`.

## The ruling

Owner ruling, 2026-10-12. Each ruling declares its kind. A build ruling links the build plan,
once for each platform it needs. A process ruling names the home that enforces it.

The format is one item per line, outside fenced text:

```
Kind: build
Plan: <path>#<slug> (<platform>)

Kind: process
Home: rule:<id>
Home: <path>
```

- Use one Plan line for each platform. `<slug>` is the anchor slug of a heading in the plan file.
- `rule:<id>` is a rule marker in CLAUDE.md. A path must be an existing file.
- Owner ruling, 2026-10-13. In another repo's pull request, a `Home: rule:<id>` resolves against
  both that repo's CLAUDE.md and the claude-settings CLAUDE.md. The action reads the second from
  its own checkout at the pinned sha, with no network read (`--rules-file`, repeatable, on the
  lint). A missing file is skipped. With none readable, a `rule:` Home is red.
- Owner ruling, 2026-10-13 14:45. q_max adopts the Kind format.
- Owner ruling, 2026-10-13 15:22. The checker is built once, here. Each repo sets its own records
  folder: `--dir <folder>` on the lint, `records-dir` on the action.
- `none` is not a kind and not a link.
- A record has one Kind line. A second ruling in the same record needs its own record.

`lint/check_ruling_kind.py` checks every record the pull request adds or changes. It runs in CI
against the pull request base. `--dir <folder>` names the records folder, relative to the
checkout. The default is `decisions`. Only `.md` files under it are checked. A `--dir` or
`records-dir` that is empty, `.`, missing, wrongly cased, or not a folder makes the lint exit
non-zero and name the folder (decision gate-hooks-fail-closed: a gate fails closed). The lint
has no "not a ruling" exemption. A record with no ruling still carries a Kind line, because
the lint cannot tell the two apart.

## The two routes

- CI lint. `lint/check_ruling_kind.py` runs in this repo's CI. The opt-in composite action
  `actions/ruling-kind` runs the same lint on another repo's pull request, against its base.
  Adopt it with `uses: shivinate7/claude-settings/actions/ruling-kind@<full-sha>` after
  `actions/checkout` with `fetch-depth: 0`. It is red when the base cannot be read.
  Its input `records-dir` names the records folder, relative to the caller's checkout. The
  default is `decisions`. q_max sets `records-dir: docs/decisions`.
- Write judge. The Write prompt judge in `settings.json` fires on any `decisions/` path. It
  refuses a record whose text has no `Kind: build` (with Plan lines) or `Kind: process` (with a
  Home line). The Edit judge sees only the changed text, so its scope is narrower (see the
  limits). Both run at write time, in any repo with these settings.

## Named limits

- The lint cannot know which platforms a ruling needs. It does not check that every platform
  has a Plan line. It checks each line that is there.
- Old records are not checked or rewritten. Each one gets its Kind line when a later change
  touches it.
- Home is checked for existence only. The lint does not check that the home enforces the ruling.
- A missing base ref reads as unknown. Locally the lint exits 0. In CI it fails.
- Only pull requests run the check. A push to main and the nightly run skip it, by design.
- The judge is a model and can miss a case. It sees only Claude's Edit and Write calls, never a
  human edit. A Bash write into `decisions/` is not judged. The Edit judge sees only the
  changed text. It cannot see a missing Kind line in an old record. Its scope is narrow.
  It refuses an edit whose new text deletes a `Kind:`, `Plan:` or `Home:` line. It also
  refuses an edit that adds a ruling section with no `Kind:` line in the same text. Only the
  Write judge and the lint check a whole record. The lint runs in no other repo yet.
- The Edit judge allowed an edit that deleted one of two `Plan:` lines (review round 3, two
  runs). No other check catches it: the lint checks only the lines that are present.
- `actions/ruling-kind/check.sh` copies the `RULE_FILES` list of the lint. No test compares the
  two lists. They match today.
- The action is not adopted anywhere yet. It has not run on a hosted runner (unmeasured).
- The lint checks that a plan heading exists. It does not check that the plan lane does the work.
- The lint refuses a `--dir` of `..` or a leading `/`, as it refuses any unusable folder.
  `actions/ruling-kind/check.sh` refuses both in `records-dir`. No test covers `..` or a leading
  `/` in either.
- `lint/check_record_slugs.py` reads `decisions/`, `deferred/` and `debts/` by default, and takes
  `--dir` for one other records folder, as this lint does. No workflow step passes `--dir` yet.

Kind: process
Home: lint/check_ruling_kind.py
