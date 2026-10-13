# Each ruling declares its kind

A decision record that a pull request adds or changes must say what kind each ruling is: a
build task, or a process change. A lint checks this on every such record.

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
- `none` is not a kind and not a link.
- A record has one Kind line. A second ruling in the same record needs its own record.

`lint/check_ruling_kind.py` checks every record the pull request adds or changes. It runs in CI
against the pull request base. It has no "not a ruling" exemption. A record with no ruling
still carries a Kind line, because the lint cannot tell the two apart.

## Named limits

- The lint cannot know which platforms a ruling needs. It does not check that every platform
  has a Plan line. It checks each line that is there.
- Old records are not checked or rewritten. Each one gets its Kind line when a later change
  touches it.
- The lint checks that a plan heading exists. It does not check that the plan lane does the work.

Kind: process
Home: lint/check_ruling_kind.py
