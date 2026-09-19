# Subagent model cap

CLAUDE.md says: "Once set up, turn each rule below into a hook or check." The rule
on a worker's model is now a cap in the harness, not a gate in a hook. This entry
records what the gate was for, why it was the wrong mechanism, and what replaces it.

## What the gate was for

CLAUDE.md said: "Justify a model above Sonnet in one line." Four commits on this
branch built `hooks/model_gate.py` to make that sentence a check. The gate ran as
a `PreToolUse` hook on `Agent` and `Workflow` calls. It read the model from the
tool payload. When the model was above Sonnet, it looked for a
`MODEL-JUSTIFICATION:` line in the prompt. With no line, it denied the call. With
a line, it asked the owner and quoted the reason. The intent was sound: keep a
worker on Sonnet unless someone made a case for more.

## Why a justification was the wrong mechanism

The gate read the reason after the orchestrator had already chosen the model. A
reason written at that point does not change the choice. It defends the choice.
Lerner and Tetlock showed this in 1999 ("Accounting for the Effects of
Accountability", Psychological Bulletin 125, 255-275). When a person expects to
justify a decision that is already made, the reasons they give are defensive
bolstering, not reconsideration. Accountability improves judgement only when it
comes before the decision, and only when the audience's view is unknown. A 2017
study of process accountability found the same shape: a demand to justify the
process changed neither accuracy nor strategy. The gate asked for the wrong thing
at the wrong time. It produced one line of text and no better choice.

The gate also had a structural cost. It had to read a model id out of a payload,
an id it could not always resolve. A `Workflow` script can set `model` through a
variable. A `fork` carries no model field at all. Each gap needed a new shape
test, and each shape test added a false ask. The four commits on this branch
show that cost. Each closed a bypass and opened a new edge.

## Why the cap is right

Claude Code has a documented setting for this: `CLAUDE_CODE_SUBAGENT_MODEL` names
the model a subagent runs, and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` makes that
name win. The sub-agents documentation says, verbatim:

```text
While `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is on, Claude Code ignores the `model`
field of every subagent definition, including the built-in Explore and Plan
subagents, and Claude can't pass a model when it starts a subagent.
```

It applies "to every subagent, teammate, and workflow agent". The setting needs
CLI 2.1.257 or later. The installed CLI is 2.1.278. CLAUDE.md: "Check whether
the primitive exists before building a workaround." The primitive exists. The
gate was the workaround.

The cap also matches the shape Anthropic documents for multi-agent work. A
frontier model orchestrates. Lower-cost models do the worker tasks. Anthropic's
model-selection matrix names sub-agent tasks under Haiku. Opus costs 2.5 times
Sonnet per token: $5 in and $25 out per million, against $2 and $10. A worker
that does one bounded task in one worktree does not need the frontier tier.

The frontier tier does pay in one place: long-horizon work over a large corpus.
Published comparisons put a Sonnet worker 10 to 12 points behind Opus on that
kind of task. That is the case the prose rule names. When a task is Opus-shaped,
the orchestrator says so before it dispatches, names why, and offers the switch.
The owner decides. The reason now comes before the choice, to an audience whose
view is unknown. That is the order Lerner and Tetlock found to work.

## What the cap does not cover

The documentation states the exception: "Two kinds of subagent still run on the
main conversation's model: a fork". A fork inherits the session's model. The cap
does not touch it. A session that runs Opus forks Opus. The prose rule in
CLAUDE.md is the only guard on a fork, and this entry records that as a known
gap. If the harness adds a cap on forks, this entry should point at it.

## Where the cap sits, and what makes lifting it visible

The cap lives in the `env` block of `settings.json`, which `install.sh` installs
as the user settings file. In the settings stack that is precedence level 5. A
project settings file at level 3 (`.claude/settings.local.json`) or level 4
(`.claude/settings.json`) overrides it. Any repo can lift the cap with one file.

Guard rule 8, `subagent-model-cap`, in `hooks/guard.py` is what makes that lift
visible. A settings write that sets or changes `CLAUDE_CODE_SUBAGENT_MODEL` or
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` asks the owner. The ask names the requested
model and the file. The cap can be lifted, but never in silence.

## The grant

An Opus worker is enabled for one session, on the owner's word in chat. The
orchestrator writes the active repo's `.claude/settings.local.json` with an
`env` block that sets both keys:

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus",
    "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"
  }
}
```

Both keys are set on purpose. If the settings stack merges `env` key by key,
the project file changes the model and keeps the force. If the stack replaces
the whole `env` block, the project file still carries the force. The grant is
correct under either merge rule. The cap holds throughout. The grant changes
which model is forced. It never lets a per-call `model` through.

That write triggers guard rule 8. The ask names the model and the file. That
prompt is the approval step. The grant can never open silently. When the work
is done, the orchestrator removes the file.

### What was measured

The build that landed this entry tested the merge rule from a subagent. It
wrote a project-local `env` block that set `CLAUDE_CODE_SUBAGENT_MODEL` to
`haiku`. The user settings set that key to `sonnet`, and set
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` to `1`. The build then read both values
from its own shell.

The result was inconclusive. The depth read `1` before and after the write. The
model was empty before and after the write. The user settings value `sonnet`
never reached the shell of the subagent. The project value `haiku` did not
reach it either. The start-time environment of the Claude Code process held
the depth and not the model. The test could not show which level wins. It could
not show whether a settings file is picked up live. The session ran on Claude
Code on the web. The installed guard there was the main-branch version, without
rule 8. The write landed without an ask.

The merge rule for `env` is unmeasured. The grant above does not depend on it,
because it sets both keys. What does depend on it is the claim that a project
file overrides user settings for this variable at all. The documentation states
that precedence. It is not yet confirmed by a measurement here. One check would
confirm it. Start a fresh local session in a repo with the grant file in place.
Spawn a worker. Read the model the worker reports.

## No per-call prompt is possible under the cap

The old gate asked at the moment of the call. The cap cannot. While
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is on, the harness drops a per-call `model`
before the tool call runs. The request never reaches the permission layer, so
no hook can ask about it. The only prompt left is the one on the settings
write, and that is where the approval now lives.

## Where this lives

This repository had no `decisions/` folder before this entry. This file starts
one, one folder per record kind. CLAUDE.md: "Give each record its own file, one
folder per kind." No number is claimed here. The file name is a slug.
CLAUDE.md: "Never allocate a numbered record on a branch. Write a slug."
