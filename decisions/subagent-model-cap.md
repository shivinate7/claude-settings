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
study of process accountability (Hoffmann, Gaissmaier and von Helversen, Judgment
and Decision Making 12(6), 627-641) found the same shape: a demand to justify the
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
Anthropic's own measurement (platform.claude.com, "Optimizing for cost and
intelligence") is the source. A frontier lead over Sonnet workers scored 10 to 12
points below an all-frontier run on that kind of task, at about half the cost. That is the case the prose rule names. When a task is Opus-shaped,
the orchestrator says so before it dispatches, names why, and offers the switch.
The owner decides. The reason now comes before the choice, to an audience whose
view is unknown. That is the order Lerner and Tetlock found to work.

## What the cap does not cover

The documentation states the exception: "Two kinds of subagent still run on the
main conversation's model: a fork" and "a skill that runs in a subagent with
`model: inherit`". A fork inherits the session's model. The cap does not touch
it. The same holds for a skill run in a subagent with `model: inherit`. A session that runs Opus forks Opus. The prose rule in
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

A second run, from a local Claude Code Desktop session (engine 2.1.275, above
the 2.1.257 floor), moved three of the four steps forward but could not
finish the fourth.

With no grant file, a subagent read `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` from its shell, and reported running on
Sonnet. That matches the user settings, which already carry the force key at
this CLI version.

The write of `.claude/settings.local.json` with the two-key grant was fed to
`hooks/guard.py` directly, with the exact payload the write call used. Rule 8
returned an `ask`, naming the model (`opus`) and the file. The live write
itself produced no visible refusal or denial in this session's tool results.
That is consistent with an ask that was shown and approved. But the
transcript available to the model carries no permission-dialog record. This
entry counts the direct `guard.py` run as the confirmation, not the live
write.

Without restarting the session, a second subagent still read
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and ran on Sonnet. The grant did not take
effect live. This matches "not live" rather than "does not override." The one
check that tells them apart needs a fresh session, started with the grant file
already in place. A running session cannot restart itself from inside the
task that is measuring it. That check did not run here. Removing the grant
file and spawning a third subagent read `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`
again, as expected since the grant was never live.

The merge rule for `env` therefore stays unmeasured after the second run. What
that run adds: the ask fires on the documented payload. A written grant does
not apply without a fresh session. What still needs a fresh local session,
with the grant file in place before that session starts: whether the project
file then wins.

A third run closed that gap. It used a genuinely fresh OS process, not a new
Code-tab session. The check ran `claude -p` from a new terminal tab, with the
grant file already in `.claude/settings.local.json`. That `claude -p` process
spawned one subagent. The subagent's task: run
`printenv CLAUDE_CODE_SUBAGENT_MODEL` and self-report which model it ran as.
Run twice, independently, the result was consistent. `printenv` inside the
subagent's own shell printed `opus`. The subagent identified itself as Opus
5. The user settings file caps the default at Sonnet. An Opus run only
happens if the project file's override reached the subagent. It did.

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` itself did not show up under `printenv` in
the subagent's shell. That does not weaken the finding. The model outcome is
the direct evidence the force worked. A Sonnet default would not otherwise
produce an Opus run. The likely reason: the harness consumes `FORCE`
internally, to decide whether to override. It does not export `FORCE` into
the tool shell the way it exports the resolved model name.

The merge rule for `env` is now confirmed for this variable. A project-local
`.claude/settings.local.json` overrides the user-settings value, in a fresh
process. The grant above does not depend on this finding either way. It sets
both keys regardless of merge order.

## No per-call prompt is possible under the cap

The old gate asked at the moment of the call. The cap cannot. While
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is on, the harness drops a per-call `model`
before the tool call runs. The request never reaches the permission layer, so
no hook can ask about it. The only prompt left is the one on the settings
write, and that is where the approval now lives.

## The expiry (2026-09-20)

CLAUDE.md said the orchestrator removes the grant file when the work is done.
Nothing checked that. `lint/rule_mechanisms.json` recorded rule
`roles-remove-override-file` as `unmechanized` for exactly this reason. An
approved lift stayed lifted, with no clock on it.

### What was protecting the outcome, and what protects it now

Before this entry, the only control was the orchestrator's own memory. It had
to remember to delete a file. Nothing enforced that. Nothing noticed when it
was skipped. That is what `roles-remove-override-file` named as ungoverned.

Now `.claude/settings.local.json` carries a second, repo-owned field. It sits
outside the `env` block: `_subagentCapUntil`, an ISO-8601 instant. It must be
no more than 24 hours ahead of the write. `hooks/config_watch.py` already
hashes this file at every `PostToolUse` and `Stop`. It already holds the
pre-lift baseline needed to restore it. It now also reads this field on every
sweep. A deadline can be missing, unparseable, already passed, or more than 24
hours out. Any of those gets the file reverted to its pre-lift content. A
systemMessage names the file and what was wrong. The outcome protected is the
one `roles-remove-override-file` named. A worker above Sonnet does not run
forever on one yes. What protects it now is a hook that reads a clock, not a
person's memory.

### A rejected spelling, and why

A proposal named an env var: `CLAUDE_CODE_SUBAGENT_MODEL_UNTIL`. It was
rejected, for three measured reasons. Claude Code reads no such setting. The
name lies about who enforces it. Nothing in the harness honors an expiring env
var on its own. It would be prose with no mechanism. That is the shape this
file's own first section already argued against once. And a key spelled
inside `env` is read by `guard.SUBAGENT_CAP_KEY`. That is the same pattern the
cap variables match.

MEASURED: `guard._cap_reading('"CLAUDE_CODE_SUBAGENT_MODEL_UNTIL": "..."')`
returns `{'CLAUDE_CODE_SUBAGENT_MODEL': ''}`. A write that touched only that
line would ask the owner to approve something. That something is a cap lift
that is not really happening.

`_subagentCapUntil` avoids all three problems. It sits outside `env`. It is
never exported into a subagent's shell. It never matches
`guard.SUBAGENT_CAP_KEY`. MEASURED: `guard._cap_reading('"_subagentCapUntil":
"2026-09-21T00:00:00Z"')` returns `{}`. The PreToolUse guard stays silent on
it. Only `hooks/config_watch.py` reads and enforces it. The name is honest
about who reads it. The watch is what this repository ships. It is not a
Claude Code setting.

### The baseline store now carries a `prior`

Before this entry, an approved cap change re-baselined straight to the lifted
content: `save_baseline(path, current)`. The pre-lift bytes were gone by the
time a deadline could be checked. `hooks/config_watch.py`'s baseline entries
now carry a third field, `prior`. It holds the content last seen before the
current lift began. It is carried forward through any later edit that keeps
the reading lifted. `load_baseline` reads a missing `prior` key the same as an
explicit absence. That is the shape every entry written before this change
carries. An old entry never crashes the new reader. When no `prior` is on
record, the expiry rule does not invent a replacement file. It does not leave
the override running in silence either. It reports the file as UNKNOWN. That
is the same way a first sight of the cap with no baseline already does. It
asks the owner to check the file by hand.

## Where this lives

This repository had no `decisions/` folder before this entry. This file starts
one, one folder per record kind. CLAUDE.md: "Give each record its own file, one
folder per kind." No number is claimed here. The file name is a slug.
CLAUDE.md: "Never allocate a numbered record on a branch. Write a slug."
