# Each ruling declares its kind

## The ruling

A decision record that a pull request adds or changes must say what kind each ruling is: a build task,
or a process change. A build ruling links the build plan, once for each platform it needs. A process
ruling names the home that enforces it. Reason: a ruling in another repo's record never became a build
task, because nothing linked the ruling to a plan. The line format is in `lint/check_ruling_kind.py`.

- `none` is not a kind and not a link. A record has one Kind line. A second ruling in the same record
  needs its own record.
- The lint has no "not a ruling" exemption, because it cannot tell the two apart. A record with no ruling
  still carries a Kind line.
- Old records are not checked or rewritten. Each one gets its Kind line when a later change touches it.
  Only pull requests run the check. A push to main and the nightly run skip it, by design.
- The lint checks every record the pull request adds or changes, against the pull request base. A
  missing base ref reads as unknown: locally the lint exits 0, in CI it fails. A bad `--dir` or
  `records-dir` makes the lint exit non-zero and name the folder (guard-hooks-fail-closed).
- In another repo's pull request, a `Home: rule:<id>` resolves against that repo's CLAUDE.md and the
  claude-settings CLAUDE.md. The action reads the second from its own checkout at the pinned sha, with no
  network read. With none readable, a `rule:` Home is red. q_max adopts the format and sets
  `records-dir: docs/decisions`.
- A message that cites a `docs/debts/` record by path is refused by cite-by-id (`git-cite-by-id`). That is
  intended.

**Two routes carry the check to the owner's other repos.**

- CI lint. The opt-in composite action `actions/ruling-kind` runs the same lint on another repo's pull
  request, against its base. It is red when the base cannot be read.
- Write judge. The Write prompt judge in `settings.json` fires on any `docs/decisions/` path. It refuses a
  record with no `Kind: build` (with Plan lines) or `Kind: process` (with a Home line). The Edit judge
  sees only the changed text. It refuses an edit that deletes a `Kind:`, `Plan:` or `Home:` line, and an
  edit that adds a ruling section with no `Kind:` line in the same text.

Kind: process
Home: lint/check_ruling_kind.py
