# Agent model cap

## The ruling

Each agent role has its own model and effort, in the table below. Sonnet is the default and the ceiling.
Opus runs only for Plan, the built-in advisor (`advisorModel`; agents inherit it), the designer and the design reviewer (owner, 2026-10-26, waiting-page item 15, "b"; decision `design-agents`), and the builder's third try by standing grant,
and the owner watches that cost. A reviewer's round 3 may run Opus on the owner's grant for that spawn.
An audit Explore may run Opus on the owner's grant, given at class level on 2026-10-21. So may the question reviewer agent hook (same class-level grant and date, see its row). Any other spawn
runs Opus only when the owner names it. A lane session or an arbiter session is a session, not an agent: it runs Opus by its row below. Round 2 stays Sonnet. Haiku runs only in Explore,
claude-code-guide, test-author, reviewer and record-writer. The guard enforces the ceiling: an Agent
or Task spawn that sets model opus asks, unless Plan, Explore, designer, design-reviewer or a builder's `Round 3 of 3` covers it.
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
| lane session (decision `session-tiers`) | opus, the owner's ruling of 2026-10-28 16:15 CDT, waiting item 50, pick b | default |
| arbiter session (decision `session-tiers`) | opus, the owner's ruling of 2026-10-29 16:42 CDT, waiting item 81, pick a | high |
| safety-classifier fallback | on, the default | n/a |
| Agent spawn judge (`hooks/call_judge.py`, PreToolUse on Agent, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| prose judge (`hooks/prose_judge.py`, PreToolUse on Edit and Write; a model call only for a path with a `decisions` folder segment) | haiku, through `decision_watch.invoke_model` | xhigh |
| reply judge (`hooks/reply_judge.py`, Stop) | haiku, through `decision_watch.invoke_model` | xhigh |
| question reviewer (the same script, on AskUserQuestion) | claude-opus-5-5, through `decision_watch.invoke_model`, by the owner's standing grant of 2026-10-21, given at class level for this hook (decision `question-reviewer-agent-hook`) | model default: the call passes no effort |
| SendMessage busy judge (`hooks/sendmessage_state.py`, PreToolUse; a model call only when the receiver is busy on the session board) | haiku, through `decision_watch.invoke_model` | xhigh |
| SendMessage wording judge (the same script, one call on every send, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| plain-diff mod note (`mods/plain-diff/hooks/register.mjs`, `$.model.complete`, one call per file with no note) | haiku, set in the call | none set: the call passes no effort field |
| decision watch (`hooks/decision_watch.py`) | haiku | xhigh |
| decision watch mod (`mods/decision-watch`, the Stop-time judge) | haiku, through `$.model.complete`, the app login; the python path above stays xhigh | session default: the call passes no effort field |
| every other hook and guard | no model; plain code | n/a |

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

**The step-up.** Guard rule `roles-third-round-steps-up` reads the `Round N of 3` marker in
the brief. A line that starts with it counts. When the brief's first non-blank line starts with no marker, the
leftmost marker on that line also counts if it is `Round N of 3`, such as "Builder, Round 3 of 3. Lane ...". A
leftmost `Try N of 3` there adds nothing. Owner ruling 2026-10-29 16:29 CDT: a round-3
builder on Opus just runs, with no approval. The first-line form is case-sensitive. Later lines count only
when they start with the marker. A builder's old `Try 3 of 3` still counts until note `try-marker-sunset`. A round 2 reviewer runs on Sonnet. A round 3 reviewer runs Sonnet, or Opus on the owner's
word. A try 3 builder needs Opus.

**No pin, and the ceiling is an ask.** The variable is a true fallback: it decides only the spawns that name no
model and whose definition names no model. `agents/builder.md` carries no `model:` key, so a builder
spawn reads the fallback. Reason: the flag collapses Claude Code's model order onto the variable. That is
a pin, not a ceiling, and it holds Opus back exactly as hard as Haiku.

**The order**, first wins: the spawn's `model` field, then the agent definition's `model:` (a built-in
definition or a pin in `agents/*.md`), then the variable, then the parent's model. The Oct 26 cases
measured `inherit` and the parent step; the Oct 27 cases measured the pin.

MEASURED in a cloud session, 2026-10-26, by each agent transcript's `model` field. The variable
was `sonnet`, and no `agents/` files were installed. A `general-purpose` spawn with no model ran
Sonnet. Built-in `Plan` and `Explore` spawns with no model ran the parent's Opus. An `Explore` spawn that set model `haiku` ran Haiku. In cloud, an Explore search runs Opus, not Haiku.

MEASURED Oct 27, cloud: this repo's `agents/*.md` copied to `~/.claude/agents`, Claude Code 2.1.311,
each case a fresh headless `claude -p` with a parent model unlike both candidates. The model came from
the run's `modelUsage` and the agent's own report of its model id. Background calls put haiku in every
`modelUsage`, so each haiku row rests on the agent's report alone. Spawns set no model unless named.

| Agent, pin | Variable | Parent | Observed |
|---|---|---|---|
| reviewer, `haiku` | sonnet | opus | haiku |
| reviewer, `haiku` | opus | sonnet | haiku |
| reviewer, `haiku` | unset | sonnet | haiku |
| reviewer, `haiku`, spawn sets `sonnet` | opus | haiku | sonnet |
| designer, `opus` | sonnet | haiku | opus |
| designer, `opus` | haiku | sonnet | opus |
| builder, no pin | haiku | sonnet | haiku |
| builder, no pin | unset | haiku | haiku |

So a pin in `agents/*.md` beats the variable in both directions. A reviewer spawn that names no model
runs Haiku even where the variable is `sonnet`; rounds 2 and 3 must set the model per spawn.
A running cloud thread does not load `~/.claude/agents` files written mid-session: its Agent tool
refused `reviewer`, `designer` and `builder` as unknown types. A process started after the write
loaded all of them. Unknown: whether the cloud thread harness itself, as against a headless run in
the same container, reads the same order.

The guard holds the ceiling by an ask (owner, 2026-10-21: Opus runs on the owner's grant, with no magic
words, and Claude never picks it alone). An Agent or Task spawn that sets model opus asks under
`agent-model-cap`, unless a standing grant covers it. A standing grant is one of: the role Plan, the role Explore (the
class-level grant above), the role designer or design-reviewer (the 2026-10-26 grant above), or a builder whose brief has the `Round 3 of 3` marker (the step-up above names the forms). A reviewer's round 3 is no standing grant, so
it asks. The owner answers the ask in the prompt, and a spawn on sonnet or haiku never asks. An override
lifts the spawn ask like any other ask (`owner-override`); the ask on a settings write under the same
id stays outside every override. The ask fires only on an Opus spawn, so it stalls a fan-out only where Opus was
asked for. A justification line is written after the model is chosen, so it defends the choice; the one line
before dispatch (`roles-opus-shaped-say-so`) names the reason before the choice, so it stays. The ask on a
write that changes the fallback stays: a write is a standing change, not a dispatch. The guard sees only
Agent and Task calls. The Opus ask never reads a Workflow `agent({model: 'opus'})` literal or a
`start_session` on Opus. The static scan of a Workflow script reads only the Haiku floor and the step-up, and a model set
through a variable is unseen by both (`floor-workflow-runtime-models`, `model-ceiling-no-after-read`).

A step grant also lifts the Opus spawn ask (owner, 2026-10-29 13:44 CDT: grants live in the roadmap).
Triage writes the owner's grant in the `grants` field of the lane's roadmap step. The step names its
lane in the field `lane`. `take()` in `hooks/override.py` reads it only on an Opus spawn ask that no Opus
override lifted. It reads the local ref `origin/roadmap` in the call's cwd and never fetches. Cost: one
`git grep` for the lane id, and one `git show` for each hit. Freshness: the lane sees a grant only after
it fetches `origin/roadmap`; until then the ask stays. Kind of risk: likely. Landed 2026-10-29. Incident:
the Opus reviewer spawn of step c202, ask-in-chat-first, waited about 2 hours on the ask.

**Measured.** (measured 2026-10-30, 5 lanes) Tokens per agent run, in thousands (k), from the lane reports. The models are the models the lane reports name. They are not checked against the table above. The lane reports name sonnet for each agent unless the line names a model.

- `small-fixes`: builder 84k; reviewer round 1 84k (4 findings); reviewer round 2 82k (0 findings).
- `wp-fit-w-one-home`: test-author 113k; builder 90k; reviewer round 1 105k (0 blocking, 3 notes).
- `triage-watches-page`: test-author 140k (2 rounds); builder 108k; reviewer round 1 108k (9 findings); reviewer round 2 94k (3 low notes).
- `handoff-no-copied-lists`: test-author 83k, 84k, 100k, 80k; builder 82k, 75k, 82k, and try 3 on opus 74k; reviewer round 1 106k (5 findings), round 2 103k (4 findings), round 3 89k (PASS, 3 notes).
- `arbiter-ruling-page-item`: designer opus 182k; test-author 100k, 134k; builder 155k, 100k; reviewer round 1 146k (6 findings), round 2 115k (2 low notes); design reviewer opus 176k (PASS 18/18).
- Side points. Step c204 (the waiting page's scrolling option picture): designers opus 175k and 187k; design reviewers opus 173k and sonnet 95k. A design reviewer run in another repo: opus 123k (1 blocker, 3 notes).

One step-down data point: the c204 design reviewer on sonnet, one step down from the table's opus, cost 95k against 173k on opus. It is the only step-down data point. The two runs are not the same task, and quality is unmeasured. For every other role, no lane ran one step down (a lower model per role). So cost and quality against one step down are unmeasured. The table names haiku for test-author, reviewer round 1 and record-writer. The lane reports name sonnet for the test-author and reviewer round 1 runs, and the numbers above hold no record-writer run. So the haiku rows are unmeasured too. Findings counts are not a quality measure. The ruling stands: keep today's table (owner, 17:50, waiting item 59, pick a).

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from them.
Before a rename or a move, find every reader: search for `agent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json
