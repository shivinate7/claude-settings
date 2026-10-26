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
| decision | A record in `docs/decisions/` for one question. It holds the ruling, the reason, and the kind and home of the ruling. | `rule:git-one-entry-per-question`, `docs/decisions/rulings-declare-kind.md` | `ADR` |
| debt | A known gap or deferred work that Claude is likely to hit in normal work. Each debt is one file in `docs/debts/`. | `docs/debts/README.md` | — |
| note | A finding that Claude is not likely to hit in normal work. Each note is one line in `docs/debts/notes.md`. | `rule:roles-holes-are-debts`, `docs/debts/notes.md` | — |
| guard | A hook rule that refuses, or asks about, one act before the act runs. It stops Claude's mistakes, not an attacker. | `hooks/guard.py`, `docs/decisions/guard-guards-mistakes-only.md` | — |
| check | A lint, test or CI job that passes or fails a change. A check never asks. | `docs/decisions/guard-guards-mistakes-only.md` | — |
| owner | The person who owns these repos. Only the owner's word makes a ruling, an override pass or a merge grant. `CLAUDE.md` speaks as the owner. | `rule:outcomes-word-covers-named-act` | — |
| override pass | A prompt from the owner that starts with `override`. The guard then lets a refusal or an ask through, once or for a set time. | `docs/decisions/owner-override-pass.md` | — |
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

## Open: one term, two meanings

Each term below has two or more meanings in this repo today. No meaning is chosen yet. Until the
owner picks one, say which meaning you use.

- **gate.** (1) A hook that can block a tool call or a reply (`docs/decisions/gate-hooks-fail-closed.md`,
  `lint/report_gate.py`). (2) Any file that enforces a rule and has a test that proves it
  (`lint/rule_audit.py`, kind `gate`), lints included.
