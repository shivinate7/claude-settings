# Each ruling declares its kind

## The ruling

A decision record that a pull request adds or changes must say what kind each ruling is: a build task,
or a process change. A build ruling links the build plan, once for each platform it needs. A process
ruling names the home that enforces it. Reason: a ruling in another repo's record never became a build
task, because nothing linked the ruling to a plan.

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
- In another repo's pull request, a `Home: rule:<id>` resolves against both that repo's CLAUDE.md and the
  claude-settings CLAUDE.md. The action reads the second from its own checkout at the pinned sha, with no
  network read (`--rules-file`, repeatable, on the lint). A missing file is skipped. With none readable,
  a `rule:` Home is red.
- q_max adopts the Kind format. The checker is built once, here. Each repo sets its own records folder:
  `--dir <folder>` on the lint, `records-dir` on the action. q_max sets `records-dir: docs/decisions`.
- `none` is not a kind and not a link.
- A record has one Kind line. A second ruling in the same record needs its own record.
- The lint has no "not a ruling" exemption. A record with no ruling still carries a Kind line, because
  the lint cannot tell the two apart.
- Old records are not checked or rewritten. Each one gets its Kind line when a later change touches it.
  Only pull requests run the check. A push to main and the nightly run skip it, by design.
- A message that cites a `debts/` record by path is refused by cite-by-id (`git-cite-by-id`). That is
  intended.

`lint/check_ruling_kind.py` checks every record the pull request adds or changes. It runs in CI against
the pull request base. A missing base ref reads as unknown: locally the lint exits 0, in CI it fails. The
default records folder is `decisions`. A bad `--dir` or `records-dir` makes the lint exit non-zero and
name the folder (a gate fails closed; gate-hooks-fail-closed).

**Two routes carry the check to the owner's other repos.**

- CI lint. The opt-in composite action `actions/ruling-kind` runs the same lint on another repo's pull
  request, against its base. Adopt it with `uses: shivinate7/claude-settings/actions/ruling-kind@<full-sha>`
  after `actions/checkout` with `fetch-depth: 0`. It is red when the base cannot be read.
- Write judge. The Write prompt judge in `settings.json` fires on any `decisions/` path. It refuses a
  record whose text has no `Kind: build` (with Plan lines) or `Kind: process` (with a Home line). The Edit
  judge sees only the changed text. It refuses an edit whose new text deletes a `Kind:`, `Plan:` or
  `Home:` line, and an edit that adds a ruling section with no `Kind:` line in the same text. Both run at
  write time, in any repo with these settings.

Kind: process
Home: lint/check_ruling_kind.py
