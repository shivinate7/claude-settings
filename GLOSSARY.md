# Glossary

This file gives each workflow thing one name. It holds only the terms that every repo uses. A
repo's own `GLOSSARY.md` holds its domain terms. A repo glossary never defines a term again that
this file defines.

Each row has the term, its meaning, its home and the names to avoid. The home is the rule or
record that defines the term. When a meaning changes, change the home first, then this row. Use
the term, never a name from its "Not" cell. `lint/check_glossary.py` fails a row whose home does not
exist. It also fails a new file path that uses a "Not" name. It reads paths, not prose.

The form comes from the `domain-modeling` skill in
[mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling):
one name for each thing, and a list of names to avoid.

## Terms

| Term | Meaning | Home | Not |
|---|---|---|---|
| lane | One isolated piece of work, with its own branch, worktree and lane PR. Its branch slug is its name. | `rule:parallelism-own-lane-orchestrator`, `docs/decisions/lane-by-slug.md` | — |
| batch | The lane PRs that join one integration branch and merge to main together. | `rule:git-integration-branch-merge` | — |
| integration branch | The branch that holds the commit of each lane in a batch. | `rule:git-integration-branch-merge` | `batch branch` |
| integration PR | The one PR of a batch that goes ready. Its CI run is the only CI run for the batch. A lone lane is its own integration PR. | `rule:git-integration-branch-merge` | — |
| worktree | A linked git working tree under `.claude/worktrees/`, for one agent. The Agent tool's isolation or the EnterWorktree tool makes it. | `docs/decisions/lanes-start-in-tool-worktrees.md` | — |
| handoff | The notes file of one session, outside git, at `~/.claude/handoffs/<session_id>.md`. The session rewrites it whole at each checkpoint, so the work survives a compaction. | `docs/decisions/precompact-handoff.md` | `handover` |
| ruling | The owner's answer to a question. | `rule:output-answer-has-a-home` | — |
| decision | A record in `docs/decisions/` for one question. It holds the ruling, the reason, and the kind and home of the ruling. | `rule:git-one-record-per-question`, `docs/decisions/rulings-declare-kind.md` | `ADR` |
| debt | An open finding or deferred work that Claude is likely to hit in normal work. Each debt is one file in `docs/debts/`. | `docs/debts/README.md` | `gap` |
| note | A finding that Claude is not likely to hit in normal work. Each note is one line in `docs/debts/notes.md`. | `rule:roles-findings-are-debts-or-notes`, `docs/debts/notes.md` | — |
| guard | A hook rule that refuses, or asks about, one act before the act runs. It stops Claude's mistakes, not an attacker. | `hooks/guard.py`, `docs/decisions/guard-guards-mistakes-only.md` | `gate` |
| check | A lint, test or CI job that passes or fails a change. A check never asks. `lint/rule_audit.py` gives a rule that a check holds the kind `check`. | `docs/decisions/guard-guards-mistakes-only.md` | `gate`, `merge gate` |
| record | One file in `docs/decisions/`, `docs/debts/` or `docs/plans/`, or one rule in `CLAUDE.md`. Its slug is its id. | `rule:git-record-own-file-per-kind`, `rule:git-one-record-per-question` | `entry` |
| finding | Anything a reviewer or an audit reports. An open finding becomes a debt or a note. | `rule:roles-findings-are-debts-or-notes` | `issue` |
| defect | Wrong behaviour in code or a check. | `rule:outcomes-tests-are-claims` | `bug` |
| round | One review and the fix after it. A change gets at most three. A builder's round N is the build or fix that review round N reads; its brief says `Round N of 3`. | `rule:roles-review-cap-three`, `rule:roles-third-round-steps-up` | `try` |
| safety hole | A guard or check that lets through an act that main refuses or asks about. Always both words. | `rule:roles-review-cap-three`, `docs/decisions/hold-unsafe-after-round-3.md` | `hole` |
| refuse | What a guard does when it stops an act. The code wraps Claude Code's own `deny` and `block` values in `refuse()`. | `hooks/guard_core.py`, `docs/decisions/guard-guards-mistakes-only.md` | `block`, `deny` |
| owner | The person who owns these repos. Only the owner makes a ruling or a grant. `CLAUDE.md` speaks as the owner. | `rule:outcomes-grant-covers-named-act` | — |
| override | A prompt from the owner that starts with `override`, or `opus` and a length. The guard then lets a refusal or an ask through, once or for a set time. An Opus override lifts only the Opus spawn ask. | `docs/decisions/owner-override.md` | `override pass` |
| grant | The owner's leave to do one act, once or standing. It covers the act it names, never a variant. A merge grant is one kind. Claude Code's own approve button is the platform's word, not a grant. | `rule:outcomes-grant-covers-named-act` | `owner word`, `approval` |
| orchestrator | The session that plans, briefs, verifies and reports. It builds only a change that cannot move a verdict. | `rule:roles-orchestrator-never-builds` | — |
| builder | An agent that does one briefed task in its own worktree and runs the check that proves the task done. A builder never reviews its own work. | `agents/builder.md` | — |
| reviewer | An agent that judges the work of a builder against its brief and the governing decisions. A reviewer never edits. | `agents/reviewer.md` | — |
| agent | Anything the Agent tool or a workflow starts. Claude Code's own names `SubagentStop`, `SubagentStart` and `subagent_type` stay as the platform spells them. | `rule:roles-one-role-per-agent` | `subagent`, `sub-agent`, `worker` |
| mutation test | A script that breaks the code on purpose, one mutant at a time, to prove the tests catch each break. | `hooks/mutate_guard.py`, `janitor/mutate_sweep.py` | `mutation harness` |
| red run | The recorded run of a test-author's new cases on the old code, where they fail. | `rule:roles-each-layer-proves-once` | `red proof` |
| step | One item of planned work on the roadmap. | `rule:speak-cite-id-plus-gloss` | — |
| CI step | One `- name:` entry in a CI job. Always say "CI step", never a bare "step". | `lint/rule_audit.py` | — |
| command | One command in a shell chain. One shell call holds one or more commands. | `docs/decisions/ask-commands-run-alone.md` | `command step` |
| designer | An agent that draws an HTML mockup of each changed screen before the builder starts. It writes only in the design folder. | `agents/designer.md` | — |
| design reviewer | An agent that judges built screens against the mockup and the repo's design rules, with a verdict per screen. It is not blind, and it never edits. | `agents/design-reviewer.md` | — |
| mockup | One HTML page in the design folder that draws a screen at every size and theme, with a notes file beside it. | `agents/designer.md` | — |
| blind lane | A designer lane whose brief names only the screen's job, users, data shapes and the house UX rules. Its brief withholds the current screen and the repo's design spec, and it is told not to read them. | `skills/design-explore/SKILL.md` | — |
| informed lane | A designer lane whose brief gives the current screen, its mockups, spec and tokens. | `skills/design-explore/SKILL.md` | — |
| directed lane | An informed lane plus one named direction, such as denser or phone first. | `skills/design-explore/SKILL.md` | — |
