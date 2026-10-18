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
  `hooks/config_watch.py`, because a clock protects better than memory.
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
the Haiku default. The caller spot-checks findings before it acts on an audit.

Haiku means Haiku 5.5.

Every skill under `skills/` has one row here: "no model pin; runs on the caller's model", because a
skill's model is the model of the session that calls it. `lint/check_skill_model_rows.py` fails CI when a
skill has no row or a row names a skill that does not exist.

**The ceiling.** Sonnet is the ceiling for every role but three standing exceptions.

- Plan runs Opus.
- The advisor is `opus`, and agents inherit it.
- The builder's third try runs Opus by the owner's standing word, and the owner watches its cost.

A reviewer's round 3 may run Opus on the owner's word for that spawn.
Round 2 stays Sonnet only. Any other agent runs Opus only on the owner's word, for the spawn the owner
names.

Prose alone enforces the ceiling, and no forcing returns. Reason: Claude Code emits no rank over models,
so a rank in a hook copies a list (`building-allow-list-is-the-constant`) and goes stale the day a model
ships. A permission prompt cannot time out, so the guard allows Opus at round 3 and the owner's word stays
prose. CLAUDE.md `roles-sonnet-is-the-ceiling` states the ceiling, and `lint/rule_mechanisms.json` records
it as `unmechanized`.

**The floor.** Haiku runs only in Explore, claude-code-guide, test-author, reviewer and record-writer.
Every other role has Sonnet as the floor. Two places enforce it, and both read one list, `HAIKU_ROLES` in
`hooks/guard.py`.

- Guard rule `subagent-model-floor` denies an `Agent` or `Task` call whose `model` holds "haiku", unless
  its `subagent_type` is a Haiku role. It reads a `Workflow` script too, denying an `agent()` call that
  names a Haiku model outside the Haiku roles. It also denies a `start_session` that names Haiku.
- `lint/check_agent_models.py`, run in `.github/workflows/gates.yml`, fails when an `agents/*.md` or
  `skills/*/SKILL.md` frontmatter sets a Haiku `model:`, unless the file is one of the Haiku roles.

`agents/plan.md` pins Plan.

**The step-up.** Guard rule `roles-third-try-steps-up` in `hooks/guard.py` reads the `Round N of 3` or
`Try N of 3` line in the brief of an `Agent` or `Task` call. A round 2 reviewer runs on Sonnet, its
ceiling. A round 3 reviewer runs Sonnet, or Opus on the owner's word. A try 3 builder needs Opus. The
Agent prompt hook in `settings.json` does not hold this check.

**The record-writer boundary.** A `record-writer` may change only `*.md` files: records, README,
CLAUDE.md-style docs. It never changes product code, tests, CI or config. Reason: a role name is only a
label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and
the floor means nothing. The guard enforces the limit at the same points as the builder and test-author
limits (builders-cannot-edit-tests). A write tool call to a non-`.md` path is denied as
`record-writer-scope`. A non-`.md` path in its diff at commit, push or stop logs `writer-diff`.
`agents/*.md`, `skills/*/SKILL.md` and output styles are `.md` but steer behaviour, and they stay in scope.

**No pin, no per-spawn gate.** Claude Code picks a spawn's model in this order: the per-invocation
`model` parameter, the subagent definition's `model` frontmatter, `CLAUDE_CODE_SUBAGENT_MODEL`, then the
main conversation's model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` collapses the order onto the variable.
That is a pin, not a ceiling: it holds Opus back exactly as hard as Haiku. The owner wants both halves
held, the ceiling by prose alone. With the flag gone, the variable is a true fallback. It decides only the
spawns that name no model and whose definition names no model. `agents/builder.md` carries no `model:`
key, so a builder spawn reads the fallback.

No per-spawn gate guards the ceiling. Reason: an ask blocks the dispatch, so a fan-out stalls at the first
ask until the owner returns. A gate also fires only on over-provisioning and is blind to
under-provisioning, and it is silent where model freedom is greatest (`guard-that-cries-wolf-is-spent`).
A justification line is the wrong mechanism: written after the model is chosen, it defends the choice and
does not change it. The one line before dispatch (`roles-opus-shaped-say-so`) names the reason before the
choice, so it stays. It asks; the owner's word decides.

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

The grant raises the fallback. It does not pin. For one Opus lane, the orchestrator passes the model on
that one call, on the owner's word: narrower and cheaper than a repository-wide raise. The grant is for
several lanes in a row, and it needs a fresh session: a running session keeps the old value.

The raise is a standing change. Every spawn in that repository that names no model reads it, and it
outlives the turn that wrote it. Two parts guard it. Both key on `CLAUDE_CODE_SUBAGENT_MODEL` and
`CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` alone.

- Guard rule `subagent-model-cap` asks on the write. The ask names the model and the file. The rule matches `_FORCE` too, so the ask still fires on a stale file, or another repository, that sets the flag.
- `hooks/config_watch.py` judges the override on every sweep. Any value of either model key other than `sonnet` lifts the cap. `_subagentCapUntil` sits outside `env`, only the watch reads it, and it must be no more than 24 hours ahead. A deadline that is missing, unparseable, passed or too far out gets the file reverted to the `prior` content the watch holds. With no `prior` on record the watch reports UNKNOWN and asks the owner to read the file by hand.

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from them.
Before a rename or a move, find every reader: search for `subagent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json
