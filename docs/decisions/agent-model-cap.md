# Agent model cap

## The ruling

Each agent role has its own model and effort, in the table below. Sonnet is the default and the ceiling.
Opus runs only for Plan, the built-in advisor (`advisorModel`; agents inherit it), the designer and the design reviewer (owner, 2026-10-26, waiting-page item 15, "b"; decision `design-agents`), and the builder's third try by standing grant,
and the owner watches that cost. A reviewer's round 3 may run Opus on the owner's grant for that spawn.
An audit Explore may run Opus on the owner's grant, given at class level on 2026-10-21. So may the question reviewer agent hook (same class-level grant and date, see its row). Any other spawn
runs Opus only when the owner names it. Round 2 stays Sonnet. Haiku runs only in Explore,
claude-code-guide, test-author, reviewer and record-writer. The guard enforces the ceiling: an Agent
or Task spawn that sets model opus asks, unless Plan, Explore, designer, design-reviewer or a builder's `Try 3 of 3` covers it.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped and stays dropped.

The default: `env.CLAUDE_CODE_SUBAGENT_MODEL` is `sonnet` in `settings.json`,
`env.CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` equals it, and `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1.
The ask on a write and the expiry of a grant are in `opus-grant-expires`, an Opus grant expires.

**The model per role.** Reason: Haiku is cheap enough for read-only work, tests, review and
record-writing, and the owner will measure cost and quality. Writing prose and records is not building.

| Point | Model | Effort |
|---|---|---|
| `CLAUDE_CODE_SUBAGENT_MODEL` | sonnet | n/a |
| Explore, claude-code-guide | haiku | xhigh |
| Explore that audits or judges meaning, not a plain search | sonnet, or opus on the owner's grant (2026-10-21 ruling, class level); set per spawn, which overrides the frontmatter `haiku` | high |
| test-author | haiku | xhigh |
| reviewer | haiku | xhigh |
| reviewer, rounds 2 and 3 | sonnet, the ceiling; round 3 may run opus on the owner's grant for that spawn; set per spawn, which overrides the frontmatter `haiku` | round 2: high, set per spawn; round 3 on sonnet: xhigh, the frontmatter; round 3 on opus: high, set per spawn |
| record-writer (`agents/record-writer.md`) | haiku | xhigh |
| builder | sonnet | high |
| builder, try 3 after a FAIL at review round 2 | opus, the owner's standing grant; set per spawn, which overrides `CLAUDE_CODE_SUBAGENT_MODEL` | high |
| Plan (`agents/plan.md`) | opus | high |
| designer (`agents/designer.md`) | opus, the owner's standing grant of 2026-10-26 | high |
| design-reviewer (`agents/design-reviewer.md`) | opus, the owner's standing grant of 2026-10-26 | high |
| general-purpose, `claude` | sonnet, by the default | model default |
| main session | unset, account default | model default |
| `fallbackModel` | sonnet | n/a |
| `advisorModel` | opus | n/a |
| fast mode | opt-in per session | n/a |
| `haiku`, `opus`, `sonnet`, `fable` aliases; `availableModels`; the `/model` picker | not pinned; no `availableModels`; built-in list | n/a |
| skills | no `model:` pin | none |
| skill `ci-hygiene` | no model pin; runs on the caller's model | none |
| skill `compliance-check` | no model pin; runs on the caller's model | none |
| skill `design-review` | no model pin; runs on the caller's model | none |
| skill `design-explore` | no model pin; runs on the caller's model | none |
| skill `fresh-prose` | no model pin; runs on the caller's model | none |
| skill `impeccable` | no model pin; runs on the caller's model | none |
| skill `plain-english-map` | no model pin; runs on the caller's model | none |
| skill `project-ops` | no model pin; runs on the caller's model | none |
| skill `ios-apps` | no model pin; runs on the caller's model | none |
| skill `roadmap` | no model pin; runs on the caller's model | none |
| skill `waiting-page` | no model pin; runs on the caller's model | none |
| cloud routines | sonnet | default |
| Claude GitHub Action, if added | haiku | xhigh |
| teammates, Workflow `agent()` | the role table, by `agentType` | the role table |
| separate sessions (`start_session`) | main model unless the owner names one | default |
| safety-classifier fallback | on, the default | n/a |
| Agent spawn judge (`hooks/call_judge.py`, PreToolUse on Agent, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| prose judge (`hooks/prose_judge.py`, PreToolUse on Edit and Write; a model call only for a path with a `decisions` folder segment) | haiku, through `decision_watch.invoke_model` | xhigh |
| reply judge (`hooks/reply_judge.py`, Stop) | haiku, through `decision_watch.invoke_model` | xhigh |
| feedback judge (`hooks/feedback_judge.py`, a detached child of `hooks/local_time.py`; runs only while `fb` capture is open and the prompt does not open with `fb`) | claude-sonnet-5-5, through `decision_watch.invoke_model` | xhigh |
| question reviewer (the same script, on AskUserQuestion) | claude-opus-5-5, through `decision_watch.invoke_model`, by the owner's standing grant of 2026-10-21, given at class level for this hook (decision `question-reviewer-agent-hook`) | model default: the call passes no effort |
| SendMessage busy judge (`hooks/sendmessage_state.py`, PreToolUse; a model call only when the receiver is busy on the session board) | haiku, through `decision_watch.invoke_model` | xhigh |
| SendMessage wording judge (the same script, one call on every send, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| plain-diff mod note (`mods/plain-diff/hooks/register.mjs`, `$.model.complete`, one call per file with no note) | haiku, set in the call | none set: the call passes no effort field |
| decision watch (`hooks/decision_watch.py`) | haiku | xhigh |
| decision watch mod (`mods/decision-watch`, the Stop-time judge) | haiku, through `$.model.complete`, the app login; the python path above stays xhigh | session default: the call passes no effort field |
| every other hook and gate | no model; plain code | n/a |

The Agent prompt judge refuses an audit Explore (a brief that asks it to audit, review, judge, rate or
compare meaning) unless the call sets model sonnet or opus; haiku or no model refuses. Explore stays a
Haiku role, so Sonnet is the floor for the judge only. Opus for an audit Explore is the owner's grant,
given at class level on 2026-10-21; the judge and the guard pass it. A plain search passes on the Haiku default. The caller
spot-checks findings before it acts on an audit.

`lint/check_skill_model_rows.py` fails CI when a skill under `skills/` has no row, or a row names a
missing skill. A skill's model is the model of the session that calls it.

Reason for prose alone at the ceiling: Claude Code emits no rank over models. A rank in a hook copies a
list (`building-allow-list-is-the-constant`) and goes stale the day a model ships. A permission prompt
cannot time out, so the guard allows Opus at round 3 and the owner's grant stays prose.

**The floor.** Every role but the five Haiku roles has Sonnet as the floor. `HAIKU_ROLES` in
`hooks/guard.py` is the one list. Guard rule `agent-model-floor` refuses an `Agent`, `Task`, `Workflow`
`agent()` or `start_session` call whose `model` holds "haiku", unless the role is a Haiku role.
`lint/check_agent_models.py` fails a Haiku `model:` in `agents/*.md` or `skills/*/SKILL.md` frontmatter,
unless the file is a Haiku role. `agents/plan.md` pins Plan.

**The step-up.** Guard rule `roles-third-try-steps-up` reads the `Round N of 3` or `Try N of 3` line in
the brief. A round 2 reviewer runs on Sonnet. A round 3 reviewer runs Sonnet, or Opus on the owner's
word. A try 3 builder needs Opus.

**No pin, and the ceiling is an ask.** The variable is a true fallback: it decides only the spawns that name no
model and whose definition names no model. `agents/builder.md` carries no `model:` key, so a builder
spawn reads the fallback. Reason: the flag collapses Claude Code's model order onto the variable. That is
a pin, not a ceiling, and it holds Opus back exactly as hard as Haiku.

MEASURED in a cloud session, 2026-10-26, by each agent transcript's `model` field. The variable
was `sonnet`, and no `agents/` files were installed. A `general-purpose` spawn with no model ran
Sonnet. Built-in `Plan` and `Explore` spawns with no model ran the parent's Opus. An `Explore` spawn that set model `haiku` ran Haiku, so the call's `model` beats both. So a definition that
names a model, `inherit` included, beats the variable. In cloud, an Explore search runs Opus, not
Haiku. Unknown: the same order for a pin in this repo's `agents/*.md`, because cloud installs none.

The guard holds the ceiling by an ask (owner, 2026-10-21: Opus runs on the owner's grant, with no magic
words, and Claude never picks it alone). An Agent or Task spawn that sets model opus asks under
`agent-model-cap`, unless a standing grant covers it. A standing grant is one of: the role Plan, the role Explore (the
class-level grant above), the role designer or design-reviewer (the 2026-10-26 grant above), or a builder whose brief has a `Try 3 of 3` line. A reviewer's round 3 is no standing grant, so
it asks. The owner answers the ask in the prompt, and a spawn on sonnet or haiku never asks. An override
lifts the spawn ask like any other ask (`owner-override`); the ask on a settings write under the same
id stays outside every override. The ask fires only on an Opus spawn, so it stalls a fan-out only where Opus was
asked for. A justification line is written after the model is chosen, so it defends the choice; the one line
before dispatch (`roles-opus-shaped-say-so`) names the reason before the choice, so it stays. The ask on a
write that changes the fallback stays: a write is a standing change, not a dispatch. The gate sees only
Agent and Task calls. The Opus ask never reads a Workflow `agent({model: 'opus'})` literal or a
`start_session` on Opus. The static scan of a Workflow script reads only the Haiku floor, and a model set
through a variable is unseen by both (`floor-workflow-runtime-models`, `model-ceiling-no-after-read`).

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from them.
Before a rename or a move, find every reader: search for `agent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json
