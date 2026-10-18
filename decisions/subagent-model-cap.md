# Subagent model cap

## The ruling

Each agent role has its own model and effort, in the table below. Sonnet is the default and the ceiling.
Opus runs only for Plan, the advisor (agents inherit it), and the builder's third try by standing word,
and the owner watches that cost. A reviewer's round 3 may run Opus on the owner's word for that spawn.
Any other spawn runs Opus only when the owner names it. Round 2 stays Sonnet. Haiku runs only in Explore,
claude-code-guide, test-author, reviewer and record-writer. Prose alone enforces the ceiling.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped and stays dropped.

The default: `env.CLAUDE_CODE_SUBAGENT_MODEL` is `sonnet` in `settings.json`,
`env.CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` equals it, and `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1.
A write that sets the fallback is always an ask (guard rule `subagent-model-cap`). `hooks/config_watch.py`
expires it, because a clock protects better than memory.

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
| `haiku`, `opus`, `sonnet`, `fable` aliases; `availableModels`; the `/model` picker | not pinned; no `availableModels`; built-in list | n/a |
| skills | no `model:` pin | none |
| skill `ci-hygiene` | no model pin; runs on the caller's model | none |
| skill `compliance-check` | no model pin; runs on the caller's model | none |
| skill `design-review` | no model pin; runs on the caller's model | none |
| skill `fresh-prose` | no model pin; runs on the caller's model | none |
| skill `impeccable` | no model pin; runs on the caller's model | none |
| cloud routines | sonnet | default |
| Claude GitHub Action, if added | haiku | xhigh |
| teammates, Workflow `agent()` | the role table, by `agentType` | the role table |
| separate sessions (`start_session`) | main model unless the owner names one | default |
| safety-classifier fallback | on, the default | n/a |
| prompt-hook judges: AskUserQuestion, Agent, Edit, Write, SendMessage (settings.json) | claude-sonnet-5-5 | model default; a prompt hook has no effort field (decision haiku-prompt-hooks) |
| reply judge (`hooks/reply_judge.py`, Stop) | haiku, through `decision_watch.invoke_model` | xhigh |
| feedback judge (`hooks/feedback_judge.py`, a detached child of `hooks/local_time.py`; runs only while `fb` capture is open and the prompt does not open with `fb`) | claude-sonnet-5-5, through `decision_watch.invoke_model` | xhigh |
| question outcome check (`hooks/question_outcome.py`) | haiku, through `decision_watch.invoke_model` | xhigh |
| SendMessage state judge (`hooks/sendmessage_state.py`, PreToolUse; a model call only when the receiver is busy on the session board) | haiku, through `decision_watch.invoke_model` | xhigh |
| plain-diff mod note (`mods/plain-diff/hooks/register.mjs`, `$.model.complete`, one call per file with no note) | haiku, set in the call | none set: the call passes no effort field |
| decision watch (`hooks/decision_watch.py`) | haiku | xhigh |
| decision watch mod (`mods/decision-watch`, the Stop-time judge) | haiku, through `$.model.complete`, the app login; the python path above stays xhigh | session default: the call passes no effort field |
| every other hook and gate | no model; plain code | n/a |

The Agent prompt judge blocks an Explore whose brief asks it to audit, review, judge, rate or compare
meaning, unless the call sets model sonnet. A plain search passes on the Haiku default. The caller
spot-checks findings before it acts on an audit.

`lint/check_skill_model_rows.py` fails CI when a skill under `skills/` has no row, or a row names a
missing skill. A skill's model is the model of the session that calls it.

Reason for prose alone at the ceiling: Claude Code emits no rank over models. A rank in a hook copies a
list (`building-allow-list-is-the-constant`) and goes stale the day a model ships. A permission prompt
cannot time out, so the guard allows Opus at round 3 and the owner's word stays prose.

**The floor.** Every role but the five Haiku roles has Sonnet as the floor. `HAIKU_ROLES` in
`hooks/guard.py` is the one list. Guard rule `subagent-model-floor` denies an `Agent`, `Task`, `Workflow`
`agent()` or `start_session` call whose `model` holds "haiku", unless the role is a Haiku role.
`lint/check_agent_models.py` fails a Haiku `model:` in `agents/*.md` or `skills/*/SKILL.md` frontmatter,
unless the file is a Haiku role. `agents/plan.md` pins Plan.

**The step-up.** Guard rule `roles-third-try-steps-up` reads the `Round N of 3` or `Try N of 3` line in
the brief. A round 2 reviewer runs on Sonnet. A round 3 reviewer runs Sonnet, or Opus on the owner's
word. A try 3 builder needs Opus.

**The record-writer boundary.** A `record-writer` may change only `*.md` files: records, README,
CLAUDE.md-style docs, agent files, skills and output styles. It never changes product code, tests, CI or
config. Reason: a role name is only a label on the spawn. With no path limit, a Haiku `record-writer` is
a Haiku builder under a new name, and the floor means nothing. The guard denies a write to a non-`.md`
path (`record-writer-scope`) and logs one in its diff at commit, push or stop (`writer-diff`).

**No pin, no per-spawn gate.** The variable is a true fallback: it decides only the spawns that name no
model and whose definition names no model. `agents/builder.md` carries no `model:` key, so a builder
spawn reads the fallback. Reason: the flag collapses Claude Code's model order onto the variable. That is
a pin, not a ceiling, and it holds Opus back exactly as hard as Haiku.

No per-spawn gate guards the ceiling. Reason: an ask blocks the dispatch, so a fan-out stalls at the first
ask until the owner returns. A gate also fires only on over-provisioning and is blind to
under-provisioning (`guard-that-cries-wolf-is-spent`). A justification line is written after the model is
chosen, so it defends the choice. The one line before dispatch (`roles-opus-shaped-say-so`) names the
reason before the choice, so it stays. It asks; the owner's word decides. One gate stays: the ask on a
write that changes the fallback. A write is a standing change, not a dispatch, so it stalls nothing
mid-fan-out.

**The grant.** An Opus worker is enabled for one repository, on the owner's word in chat
(`roles-opus-override-guarded`). The grant raises the fallback and does not pin. For one Opus lane, the
orchestrator passes the model on that one call, on the owner's word: narrower and cheaper. The grant is
for several lanes in a row, and it needs a fresh session: a running session keeps the old value.

The raise outlives the turn that wrote it. Two parts guard it. Both key on
`CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` alone.

- Guard rule `subagent-model-cap` asks on the write. It matches `_FORCE` too, so the ask still fires on a
  stale file, or another repository, that sets the flag.
- `hooks/config_watch.py` lifts the cap for any value of either model key other than `sonnet`. The
  deadline `_subagentCapUntil` is a top-level key of `.claude/settings.local.json`, outside `env`, at most
  24 hours ahead. Only the watch reads it. A deadline that is missing, unparseable, passed or too far out
  gets the file reverted to the `prior` content the watch holds. With no `prior` on record the watch
  reports UNKNOWN and asks the owner to read the file by hand.

Measured 2026-09-19 against `hooks/guard.py`: a cap lift to `.claude/settings.local.json` drew an ask
from the Write tool, a `>` redirect, a heredoc, `tee` and `jq ... > file`. It was ALLOWED from `cp`,
`mv`, `sed -i`, `python3 -c "open(path,'w')"`, `python3 gen.py` and `bash gen.sh`: the value sits in
another file or a script, so the guard cannot read it. That gap is why the watch hashes the file.

Code reads the rows of the model table, and `lint/hook_catalog.py` builds `docs/catalog.md` from them.
Before a rename or a move, find every reader: search for `subagent-model-cap`.

Kind: process
Home: lint/check_agent_models.py
Home: lint/check_skill_model_rows.py
Home: settings.json
