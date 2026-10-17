# Subagent model cap

CLAUDE.md says: "Once ready, turn each rule below into a hook or check." This entry
records how the worker-model rule is mechanized. The owner dropped
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE`. That is settled and this entry does not reopen it.

Each agent role has its own model and effort, by owner ruling 2026-10-07 (see "The model
per role"). Sonnet is the default. Haiku runs only in the roles the owner named. Opus runs
only for Plan, the advisor, the builder's third try by standing word (2026-10-12), and a
spawn the owner names.

Where each part lives:

- The default: `env.CLAUDE_CODE_SUBAGENT_MODEL` is `sonnet` in `settings.json`, and
  `env.CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` equals it. `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`
  is 1. `hooks/test_wrappers.py` checks all three.
- The floor: guard rule `subagent-model-floor`.
- The step-up: guard rule `roles-third-try-steps-up`.
- A write that sets the fallback: guard rule `subagent-model-cap`, always an ask. Its expiry:
  `hooks/config_watch.py`. The expiry exists because a clock protects better than memory.
- The ceiling: prose only.

## The model per role, ruled 2026-10-07, 2026-10-10, 2026-10-12 and 2026-10-13

The owner ruled each point in one interview. The reason: Haiku is cheap enough for
read-only work, tests, review and record-writing, and the owner will measure cost and quality.
Writing prose and records is not building.

| Point | Model | Effort |
|---|---|---|
| `CLAUDE_CODE_SUBAGENT_MODEL` | sonnet | n/a |
| Explore, claude-code-guide | haiku | xhigh |
| Explore that audits or judges meaning, not a plain search | sonnet, set per spawn, which overrides the frontmatter `haiku` | high |
| test-author | haiku | xhigh |
| reviewer | haiku | xhigh |
| reviewer, rounds 2 and 3 | sonnet, the ceiling; round 3 may run opus on the owner's word for that spawn; set per spawn, which overrides the frontmatter `haiku` | round 2: high, set per spawn; round 3 on sonnet: xhigh, the frontmatter; round 3 on opus: high, set per spawn |
| record-writer (`agents/record-writer.md`) | haiku | xhigh |
| builder | sonnet | high |
| builder, try 3 after a FAIL at review round 2 | opus, the owner's standing word of 2026-10-12; set per spawn, which overrides `CLAUDE_CODE_SUBAGENT_MODEL` | high |
| Plan (`agents/plan.md`) | opus | high |
| general-purpose, `claude` | sonnet, by the default | model default |
| main session | unset, account default | model default |
| `fallbackModel` | sonnet | n/a |
| `advisorModel` | opus | n/a |
| fast mode | opt-in per session | n/a |
| `haiku` alias | not pinned, follows Claude Code | n/a |
| skills | no `model:` pin | none |
| skill `ci-hygiene` | no model pin; runs on the caller's model | none |
| skill `compliance-check` | no model pin; runs on the caller's model | none |
| skill `design-review` | no model pin; runs on the caller's model | none |
| skill `fresh-prose` | no model pin; runs on the caller's model | none |
| skill `impeccable` | no model pin; runs on the caller's model | none |
| cloud routines | sonnet | default |
| Claude GitHub Action, if added | haiku | xhigh |
| `availableModels` | none | n/a |
| teammates, Workflow `agent()` | the role table, by `agentType` | the role table |
| separate sessions (`start_session`) | main model unless the owner names one | default |
| `opus`, `sonnet`, `fable` aliases | not pinned | n/a |
| safety-classifier fallback | on, the default | n/a |
| `/model` picker | built-in list | n/a |
| prompt-hook judges: AskUserQuestion, Agent, Edit, Write, SendMessage (settings.json) | claude-sonnet-5-5 | model default; a prompt hook has no effort field (decision haiku-prompt-hooks) |
| reply judge (`hooks/reply_judge.py`, Stop) | haiku, through `decision_watch.invoke_model` | xhigh |
| feedback judge (`hooks/feedback_judge.py`, a detached child of `hooks/local_time.py`; runs only while `fb` capture is open and the prompt does not open with `fb`) | claude-sonnet-5-5, through `decision_watch.invoke_model` | xhigh |
| question outcome check (`hooks/question_outcome.py`) | haiku, through `decision_watch.invoke_model` | xhigh |
| SendMessage state judge (`hooks/sendmessage_state.py`, PreToolUse; a model call only when the receiver is busy on the session board) | haiku, through `decision_watch.invoke_model` | xhigh |
| plain-diff mod note (`mods/plain-diff/hooks/register.mjs`, `$.model.complete`, one call per file with no note) | haiku, set in the call | none set: the call passes no effort field |
| decision watch (`hooks/decision_watch.py`) | haiku | xhigh |
| decision watch mod (`mods/decision-watch`, the Stop-time judge) | haiku, through `$.model.complete`, the app login; the python path above stays xhigh | session default: the mod passes model, prompt, maxTokens and timeoutMs only, and no effort field is known on that call; `timeoutMs` is not a known request field, and the mod enforces 50 s with its own timer |
| every other hook and gate | no model; plain code | n/a |

The Agent prompt judge checks the Explore audit row (owner ruling, 2026-10-13 12:09 CDT). It
blocks an Explore whose brief asks it to audit, review, judge, rate or compare meaning, when the
call does not set model sonnet. A plain search passes on the Haiku default. Incident: the row
rested on the session's own label, and the judge passed every Explore. The judge is a model, so
it can misread a borderline brief. The caller still spot-checks 3 findings before it acts on an
audit.

Haiku means Haiku 5.5. It needs Claude Code v2.1.293 or later. Haiku 4.5 ignores effort.
A session on an older Claude Code may run Haiku 4.5 for these roles.

Owner ruling, 2026-10-13 13:39 CDT: every skill under `skills/` has one row here. The row text is "no model pin; runs on the caller's model". The reason: a skill has no model pin, and its model is the model of the session that calls it.

A check, `lint/check_skill_model_rows.py`, fails CI when a skill has no row or a row names a skill that does not exist. It runs as two steps in the `gates` job: the check, then its fixture suite.

## Holes, named

Debts: `skill-rows-fence-indent` (a 4-space indented fence mark closes a fence). `skill-rows-test-gaps` (three shapes have no test). `skill-rows-posix-only-test` (the exit 2 test is POSIX only). `sendmessage-judge-blind-recvs` (the busy-state layer does not see some receivers). `sendmessage-judge-dup-names` (a name shared by two sessions is read as unseen). `sendmessage-wording-judge-always` (the wording judge runs on every send). `subagent-workflow-model-unasked` (a write that sets the workflow subagent model is not asked).

## Named limits

- Rows in a second table or an indented block count. The check reads rows, not table shape. This is by ruling.
- The gates steps have no step-level `if` and no `!cancelled()`. This is by design. A test pins "no if".

## The ceiling

Sonnet is the ceiling for every role but three standing exceptions, by owner rulings
2026-10-07 and 2026-10-12. Plan runs Opus. The advisor is `opus`, and agents inherit it. The
builder's third try runs Opus by the owner's standing word of 2026-10-12. The owner watches its
cost. A reviewer's round 3 may run Opus on the owner's word for that spawn (owner, 2026-10-12).
A permission prompt cannot time out in Claude Code, so the guard allows Opus at round 3 and the
owner's word stays prose. Round 2 stays Sonnet only. Any other agent runs Opus only on the
owner's word, for the spawn the owner names.

Prose alone enforces the ceiling, and no forcing returns (owner, 2026-09-28). A hook cannot
hold it. Claude Code emits no rank over models, so a rank in a hook copies a list
(`building-allow-list-is-the-constant`) and goes stale the day a model ships. CLAUDE.md
`roles-sonnet-is-the-ceiling` states the ceiling, and `lint/rule_mechanisms.json` records it as
`unmechanized`.

## The floor

Haiku runs only in Explore, claude-code-guide, test-author, reviewer and record-writer. Every
other role has Sonnet as the floor. Two places enforce it. Both read one list, `HAIKU_ROLES` in
`hooks/guard.py`.

- Guard rule `subagent-model-floor` in `hooks/guard.py` denies an `Agent` or `Task` call whose
  `model` holds "haiku", unless its `subagent_type` is a Haiku role. It reads a `Workflow` script
  too: it denies an `agent()` call that names a Haiku model outside the Haiku roles. It also
  denies a `start_session` that names Haiku.
- `lint/check_agent_models.py`, run in `.github/workflows/gates.yml`, fails when an
  `agents/*.md` or `skills/*/SKILL.md` frontmatter sets a Haiku `model:`, unless the file is one
  of the Haiku roles.

The floor has no CLAUDE.md anchor (decision `claude-md-shrink`, guard and gate rules leave the
prose).

The Workflow check reads string literals in each `agent(` call. It does not see a model or role
built at run time. Examples: a variable, a spread, an alias, a concatenation, a ternary, a
computed key, a template `${}`. A regex literal that holds a quote also hides the call that
follows it. Known limit: a built-in agent with no file here picks its own model and never puts
it in the tool input. Measured 2026-10-07: the built-in Plan ran Opus 5.5 and general-purpose
ran Sonnet 5.5. `agents/plan.md` now pins Plan.

## The step-up

Guard rule `roles-third-try-steps-up` in `hooks/guard.py` reads the `Round N of 3` or
`Try N of 3` line in the brief of an `Agent` or `Task` call. A round 2 reviewer runs on Sonnet,
its ceiling. A round 3 reviewer runs Sonnet, or Opus on the owner's word. A try 3 builder needs
Opus. The Agent prompt hook in `settings.json` does not hold this check.

Named limits:

- Only a line that starts with `Round N of 3` or `Try N of 3` counts. `Round 2/3`,
  `- Round 2 of 3`, `**Round 2 of 3**` and `# Round 2 of 3` pass unseen.
- The role compare is exact, so a plugin type such as `x:reviewer` is not checked.
- A `Workflow` script `agent()` call is not checked.
- The reviewer test is a substring match on "sonnet". A made-up model such as `opus-sonnet`
  passes. No real model id holds both names.
- A round 1 reviewer brief with a prose line that starts `Round 2 of 3` is denied. The refusal
  names the fix.

## The record-writer boundary, ruled 2026-10-10

A `record-writer` may change only `*.md` files: records, README, CLAUDE.md-style docs. It never
changes product code, tests, CI or config. The risk: a role name is only a label on the spawn.
With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and the floor
above means nothing. The guard enforces the limit at the same points as the builder and
test-author limits (builders-cannot-edit-tests). A write tool call to a non-`.md` path is denied
as `record-writer-scope`, by the path as given. A non-`.md` path in its diff at commit, push or
stop logs `writer-diff`; that also catches a `.md` link to another file.

Known limit: `agents/*.md`, `skills/*/SKILL.md` and output styles are `.md` but steer behaviour.
The ruling names CLAUDE.md-style docs, so they stay in scope. `lint/check_agent_models.py` still
catches a Haiku `model:` pin written into one.

## The precedence

The sub-agents documentation gives this order. The first entry that names a model wins.

1. The per-invocation `model` parameter.
2. The subagent definition's `model` frontmatter. A value of `inherit` means that the
   main conversation's model applies.
3. `CLAUDE_CODE_SUBAGENT_MODEL`.
4. The main conversation's model.

Four dated behaviour changes bound any reasoning about this order.

- Before v2.1.251, `CLAUDE_CODE_SUBAGENT_MODEL` came first. It beat both the
  per-call parameter and the frontmatter. The order then reversed. Anything argued
  before that version is wrong about this.
- Before v2.1.196, `CLAUDE_CODE_SUBAGENT_MODEL=inherit` forced the main model.
  Today that value does nothing.
- In v2.1.211, a per-invocation model started to survive a subagent resume.
- In v2.1.257, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` arrived.

## No pin, no per-spawn gate

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` collapses the whole order onto entry 3. That is a pin, not
a ceiling: it holds Opus back exactly as hard as Haiku. The owner wants both halves held, the
ceiling by prose alone. A pin cannot match a tier to a lane in either direction. With the flag
gone:

- The variable is a true fallback. At entry 3 it decides only the spawns that name no model and
  whose definition names no model. `agents/builder.md` carries no `model:` key, so a builder
  spawn reads the fallback.
- A per-call model reaches the tool payload, so a `PreToolUse` hook on `Agent` can read the
  model a spawn names.
- A spawn that names nothing still runs Sonnet.

No per-spawn gate guards the ceiling. Three reasons, in order of weight:

- An ask blocks the dispatch. A fan-out of four lanes stalls at the first ask until the owner
  returns. The gate costs parallelism, not tokens.
- A gate fires on over-provisioning, which costs 2.5 times the tokens of one lane. It is blind
  to under-provisioning, which costs a rework cycle: a lane runs 25 to 60 minutes, and a retry
  re-sends the full context. A cheaper model that fails more often costs more per solved task.
- A gate covers by shape. An `Agent` call shows its model. A `Workflow` script that computes
  `model` in a variable, a fork, and a skill run in a subagent with `model: inherit` show none.
  A gate silent where model freedom is greatest gives false confidence.
  `guard-that-cries-wolf-is-spent` names the opposite failure.

A justification line is the wrong mechanism. The deleted gate, `hooks/model_gate.py`, ran on
`Agent` and `Workflow` calls. Above Sonnet, it denied a spawn with no `MODEL-JUSTIFICATION:`
line in the prompt, and asked the owner when the line was there. The reason is written after
the model is chosen, so it defends the choice and does not change it. Sources:

- Lerner and Tetlock, 1999, Psychological Bulletin 125: 255-275.
- Hoffmann, Gaissmaier and von Helversen, 2017, Judgment and Decision Making 12: 627-641. A
  demand for a justification changed neither accuracy nor strategy.

A gate that reads a model id from a payload it cannot always resolve needs a new shape test for
each gap. Each test adds a false ask. Four commits built `hooks/model_gate.py`. Each closed a
bypass and opened an edge. The one line before dispatch (`roles-opus-shaped-say-so`)
fits the evidence. It names the reason before the choice, to an audience whose view is unknown.

One gate stays: guard rule `subagent-model-cap` asks on a write that changes the fallback. A
write is a standing change, not a dispatch, so the ask stalls nothing mid-fan-out.

## The outcome evidence

Gathered 2026-09-22. It points one way on tiering and the other way on pinning.

For tiering down. The floor now limits Haiku to the named roles. Anthropic's multi-agent research reports a 90.2 percent gain over
a single-agent Opus run, by distributing work to Sonnet subagents with isolated context. The
Opus 4.5 system card shows an Opus orchestrator with Sonnet 4.5 subagents at 85.4 percent.
Subagent choice moves end-to-end results. Routing guides report a 5 to 10 times cost reduction
with Haiku subagents on retrieval and pattern work. No public benchmark covers the tasks Haiku
is recommended for, so the SWE-bench gap probably overstates the difference on those tasks.

Against any static pin. The metric is cost per solved task. A cheaper model that fails more
often costs more once retries count. A retry re-sends the full context, so two retries can
triple a session's cost. A June 2026 preprint catalogued 63 budget-overrun incidents across 21
orchestration frameworks, with retry loops as a named failure class. Static routing breaks when
task complexity varies inside one role.

In this repository, the same day, lanes varied. Two lanes were mechanical. Two needed real
diagnosis, and both caught errors their brief did not anticipate. A lane runs 25 to 60 minutes
of wall-clock time. A rework cycle costs far more than over-provisioning one lane by 2.5 times
the tokens.

The error costs are asymmetric. Under-provisioning costs a rework cycle. Over-provisioning
costs 2.5 times the tokens of one lane. The cheap error is the one the pin was built to prevent.

## What the orchestrator owes at dispatch time

The one line before dispatch (`roles-opus-shaped-say-so`) is the right shape and the right
order. The reason comes before the choice, to an audience whose view is unknown. Lerner and
Tetlock found that condition to work. The justification gate, since deleted, failed it. Keep
the line.

It is not enough, for two reasons.

- It names only the up direction. No departure below Sonnet exists, so the line is owed for a
  departure up. The line asks; the owner's word decides.
- Nothing after the fact can read which tier ran. The report names every dispatch, but not the
  model. A Done line for a lane should name the tier when the tier was not Sonnet. That is a
  report-format change. `lint/report_gate.py` cannot check it, because nothing tells the gate
  what model a lane actually ran.

## The grant

An Opus worker is enabled for one repository, on the owner's word in chat. The orchestrator
writes `.claude/settings.local.json`:

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus"
  },
  "_subagentCapUntil": "<ISO-8601 time, at most 24 hours ahead>"
}
```

The grant raises the fallback. It does not pin. An orchestrator that wants one Opus lane passes
the model on that one call, on the owner's word: narrower and cheaper than a repository-wide
raise. The grant is for several lanes in a row.

The raise is a standing change. Every spawn in that repository that names no model reads it, and
it outlives the turn that wrote it. Two parts guard it. Both key on the model variable alone.

- Guard rule `subagent-model-cap` asks on the write. The ask names the model and the file. The
  rule matches the model key with an optional `_FORCE` group. The group stays, so the ask still
  fires on a stale file, or another repository, that sets the flag.
- `hooks/config_watch.py` judges the override on every sweep. `cap_lift_value` returns true for
  any value of `CLAUDE_CODE_SUBAGENT_MODEL` other than `sonnet`. `_subagentCapUntil` sits outside
  `env`, only the watch reads it, and it must be no more than 24 hours ahead. A deadline that is
  missing, unparseable, passed or too far out gets the file reverted to the `prior` content the
  watch holds. With no `prior` on record the watch reports UNKNOWN and asks the owner to read
  the file by hand.

## What was measured

- A project-local `.claude/settings.local.json` overrides the user-settings value of
  `CLAUDE_CODE_SUBAGENT_MODEL` in a fresh process. `claude -p` from a new terminal tab, with the
  grant file in place, spawned a subagent whose own `printenv` printed `opus`, twice,
  independently. The user settings hold `sonnet`.
- A written grant does not apply to a session already running. A second subagent in the same
  session still read `sonnet`. The grant needs a fresh session.
- Guard rule `subagent-model-cap` fires on the documented payload. Fed the exact write call, it
  returned an ask naming the model and the file.
- A cap reading over a line that holds only `_subagentCapUntil` returns an empty mapping. The
  ask stays silent on a write that touches only the deadline.

## What stays uncovered, on purpose

- A fork runs the main conversation's model, and so does a skill run in a subagent with
  `model: inherit`. Only the prose rule guards them.
- A spawn above Sonnet with no word from the owner passes without a prompt. Only prose forbids
  it, by owner ruling. Nothing reads it after the turn: the Stop guardrail judges on-disk
  changes only. The spend it lets through is one lane at 2.5 times cost. This entry accepts that.
- Under-provisioning is caught by nothing before the rework cycle, except the step-up and the
  floor.
- No check reads which tier a lane ran, so nothing checks that a Done line names a tier above
  Sonnet (see "What the orchestrator owes at dispatch time"). `lint/report_gate.py` cannot see
  the model.
- Removing the override file before its expiry has no check (debt `override-removal-unreminded`).

## Where this lives

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from
them. Before a rename or a move, find every reader: search for `subagent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json
