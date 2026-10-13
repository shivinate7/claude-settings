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
- `none` is not a kind and not a link.
- A record has one Kind line. A second ruling in the same record needs its own record.

`lint/check_ruling_kind.py` checks every record the pull request adds or changes. It runs in CI
against the pull request base. It has no "not a ruling" exemption. A record with no ruling
still carries a Kind line, because the lint cannot tell the two apart.

## The two routes

- CI lint. `lint/check_ruling_kind.py` runs in this repo's CI. The opt-in composite action
  `actions/ruling-kind` runs the same lint on another repo's pull request, against its base.
  Adopt it with `uses: shivinate7/claude-settings/actions/ruling-kind@<full-sha>` after
  `actions/checkout` with `fetch-depth: 0`. It is red when the base cannot be read.
- Write judge. The Edit and Write prompt judges in `settings.json` fire on any `decisions/`
  path. They refuse a record whose written text has no `Kind: build` (with Plan lines) or
  `Kind: process` (with a Home line). The check runs at write time, in any repo with these
  settings. Only the Write judge sees a whole record.

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
- `actions/ruling-kind/check.sh` copies the `RULE_FILES` list of the lint. If the two drift,
  the check fails red.
- The action is not adopted anywhere yet. It has not run on a hosted runner (unmeasured).
- The lint checks that a plan heading exists. It does not check that the plan lane does the work.

Kind: process
Home: lint/check_ruling_kind.py
