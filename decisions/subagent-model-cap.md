# Subagent model cap

## The ruling

This entry mechanizes the worker-model rule. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped and stays dropped.

Each agent role has its own model and effort. Sonnet is the default. Haiku runs only in the roles the
owner named. Opus runs only for Plan, the advisor, the builder's third try by standing word, and a spawn
the owner names.

Where each part lives:

- The default: `env.CLAUDE_CODE_SUBAGENT_MODEL` is `sonnet` in `settings.json`, and
  `env.CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` equals it. `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1.
  `hooks/test_wrappers.py` checks all three.
- The floor: guard rule `subagent-model-floor`.
- The step-up: guard rule `roles-third-try-steps-up`.
- A write that sets the fallback: guard rule `subagent-model-cap`, always an ask. Its expiry:
  `hooks/config_watch.py`. The expiry exists because a clock protects better than memory.
- The ceiling: prose only.

**The model per role.** Reason: Haiku is cheap enough for read-only work, tests, review and
record-writing, and the owner will measure cost and quality. Writing prose and records is not building.

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
| builder, try 3 after a FAIL at review round 2 | opus, the owner's standing word; set per spawn, which overrides `CLAUDE_CODE_SUBAGENT_MODEL` | high |
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

The Agent prompt judge checks the Explore audit row. It blocks an Explore whose brief asks it to audit,
review, judge, rate or compare meaning, when the call does not set model sonnet. A plain search passes on
the Haiku default. The judge is a model, so it can misread a borderline brief. The caller still
spot-checks 3 findings before it acts on an audit.

Haiku means Haiku 5.5. It needs Claude Code v2.1.293 or later. Haiku 4.5 ignores effort. A session on an
older Claude Code may run Haiku 4.5 for these roles.

Every skill under `skills/` has one row here. The row text is "no model pin; runs on the caller's model",
because a skill's model is the model of the session that calls it. `lint/check_skill_model_rows.py` fails
CI when a skill has no row or a row names a skill that does not exist. It runs as two steps in the `gates`
job: the check, then its fixture suite. Rows in a second table or an indented block count, because the
check reads rows, not table shape. The gates steps have no step-level `if` and no `!cancelled()`. This is
by design, and a test pins "no if".

**The ceiling.** Sonnet is the ceiling for every role but three standing exceptions. Plan runs Opus. The
advisor is `opus`, and agents inherit it. The builder's third try runs Opus by the owner's standing word,
and the owner watches its cost. A reviewer's round 3 may run Opus on the owner's word for that spawn. A
permission prompt cannot time out in Claude Code, so the guard allows Opus at round 3 and the owner's word
stays prose. Round 2 stays Sonnet only. Any other agent runs Opus only on the owner's word, for the spawn
the owner names.

Prose alone enforces the ceiling, and no forcing returns. A hook cannot hold it. Claude Code emits no rank
over models, so a rank in a hook copies a list (`building-allow-list-is-the-constant`) and goes stale the
day a model ships. CLAUDE.md `roles-sonnet-is-the-ceiling` states the ceiling, and
`lint/rule_mechanisms.json` records it as `unmechanized`.

**The floor.** Haiku runs only in Explore, claude-code-guide, test-author, reviewer and record-writer.
Every other role has Sonnet as the floor. Two places enforce it, and both read one list, `HAIKU_ROLES` in
`hooks/guard.py`.

- Guard rule `subagent-model-floor` denies an `Agent` or `Task` call whose `model` holds "haiku", unless
  its `subagent_type` is a Haiku role. It reads a `Workflow` script too: it denies an `agent()` call that
  names a Haiku model outside the Haiku roles. It also denies a `start_session` that names Haiku.
- `lint/check_agent_models.py`, run in `.github/workflows/gates.yml`, fails when an `agents/*.md` or
  `skills/*/SKILL.md` frontmatter sets a Haiku `model:`, unless the file is one of the Haiku roles.

The floor has no CLAUDE.md anchor (`claude-md-shrink`). The Workflow check reads string literals in each
`agent(` call. It does not see a model or role built at run time: a variable, a spread, an alias, a
concatenation, a ternary, a computed key, or a template `${}`. A regex literal that holds a quote also
hides the call that follows it. A built-in agent with no file here picks its own model and never puts it
in the tool input. `agents/plan.md` pins Plan.

**The step-up.** Guard rule `roles-third-try-steps-up` in `hooks/guard.py` reads the `Round N of 3` or
`Try N of 3` line in the brief of an `Agent` or `Task` call. A round 2 reviewer runs on Sonnet, its
ceiling. A round 3 reviewer runs Sonnet, or Opus on the owner's word. A try 3 builder needs Opus. The
Agent prompt hook in `settings.json` does not hold this check. Named limits:

- Only a line that starts with `Round N of 3` or `Try N of 3` counts. `Round 2/3`, `- Round 2 of 3`, `**Round 2 of 3**` and `# Round 2 of 3` pass unseen.
- The role compare is exact, so a plugin type such as `x:reviewer` is not checked.
- A `Workflow` script `agent()` call is not checked.
- The reviewer test is a substring match on "sonnet". A made-up model such as `opus-sonnet` passes.
- A round 1 reviewer brief with a prose line that starts `Round 2 of 3` is denied. The refusal names the fix.

**The record-writer boundary.** A `record-writer` may change only `*.md` files: records, README,
CLAUDE.md-style docs. It never changes product code, tests, CI or config. Reason: a role name is only a
label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and
the floor means nothing. The guard enforces the limit at the same points as the builder and test-author
limits (builders-cannot-edit-tests). A write tool call to a non-`.md` path is denied as
`record-writer-scope`, by the path as given. A non-`.md` path in its diff at commit, push or stop logs
`writer-diff`, which also catches a `.md` link to another file. `agents/*.md`, `skills/*/SKILL.md` and
output styles are `.md` but steer behaviour, and they stay in scope. `lint/check_agent_models.py` still
catches a Haiku `model:` pin written into one.

**The precedence.** The sub-agents documentation gives this order. The first entry that names a model wins.

1. The per-invocation `model` parameter.
2. The subagent definition's `model` frontmatter. A value of `inherit` means that the main conversation's model applies.
3. `CLAUDE_CODE_SUBAGENT_MODEL`.
4. The main conversation's model.

Version bounds: before v2.1.251, `CLAUDE_CODE_SUBAGENT_MODEL` came first and beat both the per-call
parameter and the frontmatter. Before v2.1.196, `CLAUDE_CODE_SUBAGENT_MODEL=inherit` forced the main
model. Today that value does nothing. A per-invocation model survives a subagent resume since v2.1.211.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` arrived in v2.1.257.

**No pin, no per-spawn gate.** `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` collapses the whole order onto entry
3. That is a pin, not a ceiling: it holds Opus back exactly as hard as Haiku. The owner wants both halves
held, the ceiling by prose alone. With the flag gone, the variable is a true fallback. At entry 3 it
decides only the spawns that name no model and whose definition names no model. `agents/builder.md`
carries no `model:` key, so a builder spawn reads the fallback. A per-call model reaches the tool payload,
so a `PreToolUse` hook on `Agent` can read the model a spawn names. A spawn that names nothing still runs
Sonnet.

No per-spawn gate guards the ceiling. Three reasons, in order of weight:

- An ask blocks the dispatch. A fan-out of four lanes stalls at the first ask until the owner returns. The gate costs parallelism, not tokens.
- A gate fires on over-provisioning, which costs 2.5 times the tokens of one lane. It is blind to under-provisioning, which costs a rework cycle. A cheaper model that fails more often costs more per solved task.
- A gate covers by shape. An `Agent` call shows its model. A `Workflow` script that computes `model` in a variable, a fork, and a skill run in a subagent with `model: inherit` show none. A gate silent where model freedom is greatest gives false confidence (`guard-that-cries-wolf-is-spent`).

A justification line is the wrong mechanism. The reason is written after the model is chosen, so it
defends the choice and does not change it. A demand for a justification changed neither accuracy nor
strategy (Lerner and Tetlock 1999; Hoffmann, Gaissmaier and von Helversen 2017). A gate that reads a model
id from a payload it cannot always resolve needs a new shape test for each gap, and each test adds a false
ask. The one line before dispatch (`roles-opus-shaped-say-so`) fits the evidence: it names the reason
before the choice, to an audience whose view is unknown. It names only the up direction. The line asks;
the owner's word decides.

One gate stays: guard rule `subagent-model-cap` asks on a write that changes the fallback. A write is a
standing change, not a dispatch, so the ask stalls nothing mid-fan-out.

**The grant.** An Opus worker is enabled for one repository, on the owner's word in chat. The
orchestrator writes `.claude/settings.local.json`:

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus"
  },
  "_subagentCapUntil": "<ISO-8601 time, at most 24 hours ahead>"
}
```

The grant raises the fallback. It does not pin. An orchestrator that wants one Opus lane passes the model
on that one call, on the owner's word: narrower and cheaper than a repository-wide raise. The grant is for
several lanes in a row. The grant needs a fresh session: a session already running keeps the old value.

The raise is a standing change. Every spawn in that repository that names no model reads it, and it
outlives the turn that wrote it. Two parts guard it. Both key on the model variables alone:
`CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL`.

- Guard rule `subagent-model-cap` asks on the write. The ask names the model and the file. The rule matches either model key with an optional `_FORCE` group. The group stays, so the ask still fires on a stale file, or another repository, that sets the flag. A cap reading over a line that holds only `_subagentCapUntil` returns an empty mapping, so the ask stays silent on a write that touches only the deadline.
- `hooks/config_watch.py` judges the override on every sweep. `cap_lift_value` returns true for any value of either model key other than `sonnet`. `_subagentCapUntil` sits outside `env`, only the watch reads it, and it must be no more than 24 hours ahead. A deadline that is missing, unparseable, passed or too far out gets the file reverted to the `prior` content the watch holds. With no `prior` on record the watch reports UNKNOWN and asks the owner to read the file by hand.

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from them.
Before a rename or a move, find every reader: search for `subagent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json

## Holes, named

Debts: `skill-rows-fence-indent`, `skill-rows-test-gaps`, `skill-rows-posix-only-test`,
`sendmessage-judge-blind-recvs`, `sendmessage-judge-dup-names`, `sendmessage-wording-judge-always`,
`override-removal-unreminded` (removing the override file before its expiry has no check).

## What stays uncovered, on purpose

- A fork runs the main conversation's model, and so does a skill run in a subagent with `model: inherit`. Only the prose rule guards them.
- A spawn above Sonnet with no word from the owner passes without a prompt. Only prose forbids it. Nothing reads it after the turn: the Stop guardrail judges on-disk changes only. The spend it lets through is one lane at 2.5 times cost. This entry accepts that.
- Under-provisioning is caught by nothing before the rework cycle, except the step-up and the floor.
- No check reads which tier a lane ran, so nothing checks that a Done line names a tier above Sonnet. `lint/report_gate.py` cannot see the model.
