# Subagent model cap

CLAUDE.md says: "Once ready, turn each rule below into a hook or check." This entry
records how the worker-model rule is mechanized after
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped. The owner dropped it. That is settled
and this entry does not reopen it.

The short answer: Sonnet is the floor and the ceiling for every agent. The ceiling is
prose only, by owner ruling (see "The ceiling, ruled 2026-09-28").
`CLAUDE_CODE_SUBAGENT_MODEL: sonnet` stays as the fallback, so nothing moves by default. The settings-write ask and the
expiry both stay, because both key on the model variable and never on the force flag.
One floor gate is added: no subagent runs Haiku (see the next section).

## The ceiling, ruled 2026-09-28

The owner ruled: "Every one of your agents must be on sonnet only. Opus as an agent is
only used if I tell you." Sonnet is also the ceiling. An agent runs Opus, or any model
above Sonnet, only on the owner's word, for the spawn the owner names. The reason: the
owner wants Sonnet on every lane, whatever the cost.

Enforcement stays prose only, by owner ruling. The owner will not bring back the
forcings, because prose alone is strong enough to mandate it. No hook and no
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` enforces the ceiling. CLAUDE.md
`roles-sonnet-is-the-ceiling` states it, and `lint/rule_mechanisms.json` records it as
`unmechanized` with the ruling as reason. The owner's word is the only path to Opus:
the `roles-opus-shaped-say-so` line, and then the guarded
`settings.local.json` raise, which the owner must also order.

## The floor, ruled 2026-09-28

The owner ruled: "disallow haiku for anything." Sonnet is the floor for every lane.
The reason: the owner prefers Sonnet's quality on every lane, whatever the cost. This
reverses the part of this entry that reopened Haiku when the force pin was dropped.

Three places enforce it.

- Guard rule `subagent-model-floor` in `hooks/guard.py` denies an `Agent` or `Task`
  call whose `model` holds "haiku". Any case and any full id match.
- `lint/check_agent_models.py`, run in `.github/workflows/gates.yml`, fails when an
  `agents/*.md` or `skills/*/SKILL.md` frontmatter sets a Haiku `model:`. A file's own
  key names no model in the tool input, so the guard cannot see it.
- CLAUDE.md `roles-sonnet-is-the-floor` states the floor.

Known limit. A built-in agent that picks its own model inside Claude Code never puts
that model in the tool input, and it has no file here. The guard and the check cannot
reach it. Per the sub-agents docs, one built-in runs Haiku: `claude-code-guide`. This
change does not cover it. Explore is not a limit: since v2.1.198 it inherits the main
conversation's model, and the custom `Explore` in `agents/explore.md` (PR #179)
overrides the built-in with `model: sonnet`. The other built-ins (Plan, general-purpose,
`claude`, `statusline-setup`) inherit or run Sonnet. A `model` named on the call
reaches the guard, so the floor holds for any spawn that names one.

Other sections below keep their Haiku sentences only as evidence of the earlier
argument. The floor overrides them.

## The precedence, corrected

The sub-agents documentation gives this order. The first entry that names a model
wins.

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

## A pin is not a ceiling

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` collapses the whole order onto entry 3. Every
other entry is dropped before the tool call runs. That is a pin, not a ceiling. It
held Opus back exactly as hard as it held Haiku back. The owner wants both halves
held, but the ceiling by prose alone, with no pin. The floor blocks Haiku by its own
rule.

The earlier version of this entry called the pin a cap. That word was wrong, and the
wrong word hid the cost. The rule the owner wants is about matching a tier to a lane.
A pin cannot express that rule in either direction.

## What dropping the force flag changes

Three things change, and each one matters to a question below.

The variable becomes a true fallback. At entry 3 it decides only the spawns that name
no model and whose definition names no model. MEASURED 2026-09-22: neither
`~/.claude/agents/builder.md` nor `~/.claude/agents/reviewer.md` carries a `model:`
key. Both roles therefore read the fallback. The default has a real subject.

A per-call model reaches the tool payload again. Under the pin, the harness dropped
that field before the permission layer saw it, so no hook could read it. Entry 1 is
live again. A `PreToolUse` hook on `Agent` can now read the model a spawn names.

Nothing shifts by default. The fallback value stays `sonnet`, so a spawn that names
nothing still runs Sonnet, exactly as it did under the pin.

## The outcome evidence

Gathered 2026-09-22. It points one way on tiering and the other way on pinning.

For tiering down (superseded by the floor, kept as evidence). Anthropic's multi-agent research reports a 90.2 percent gain over a
single-agent Opus run, by distributing work to Sonnet subagents with isolated
context. The Opus 4.5 system card shows an Opus orchestrator with Sonnet 4.5
subagents at 85.4 percent. Subagent choice moves end-to-end results. Routing guides
report a 5 to 10 times cost reduction with Haiku subagents on retrieval and pattern
work. No public benchmark covers the tasks Haiku is actually recommended for, so the
SWE-bench gap probably overstates the difference on those tasks.

Against any static pin. The metric is cost per solved task. A cheaper model that
fails more often costs more once retries are counted. A retry re-sends the full
context, so two retries can triple a session's cost. A June 2026 preprint catalogued
63 budget-overrun incidents across 21 orchestration frameworks, with retry loops as a
named failure class. Static routing breaks when task complexity varies inside one
role.

Observed in this repository, same day. Lanes vary. Two lanes were
mechanical. Two needed real diagnosis, and both caught errors their brief did not
anticipate. A lane runs 25 to 60 minutes of wall-clock time. A rework cycle therefore
costs far more than over-provisioning one lane by 2.5 times the tokens.

The error costs are asymmetric. Under-provisioning costs a rework cycle.
Over-provisioning costs 2.5 times the tokens of one lane. The cheap error is the one
the pin was built to prevent.

## Question 1. The expiry machinery

It is not dead code, and it needs no edit.

The whole apparatus keys on the model variable alone. `cap_lift_value` in
`hooks/config_watch.py` reads `CLAUDE_CODE_SUBAGENT_MODEL` and returns true for any
value other than `sonnet`. The force flag never enters that test. Guard rule 8 in
`hooks/guard.py` matches the model key with an optional `_FORCE` group beside it.
Drop the flag and the optional group simply stops matching.

What the expiry guards is still there. A project file that writes
`CLAUDE_CODE_SUBAGENT_MODEL: opus` no longer pins anything. It still raises the
default for every spawn in that repository that names no model. That is a standing,
session-wide change that outlives the turn that wrote it. An approved raise that
stays raised forever is the exact outcome `roles-remove-override-file` named as
ungoverned. A clock still protects it better than a person's memory.

So the machinery changes subject, not shape. It stops guarding the lift of a pin. It
guards the raise of a default. Both CLAUDE.md anchors survive with new words.
`hooks/config_watch.py` and its 28-case suite in `hooks/test_config_watch.py` stay
byte-for-byte. The force flag appears in those fixtures as file content. It is never
a behaviour the suite asserts. The fixtures keep passing, and they keep exercising
the optional group.

Keep the optional `_FORCE` group in the guard pattern. It costs one group. It keeps
the ask firing on a stale file, or on another repository, that still sets the flag.

## Question 2. How a gate would know what is above Sonnet

There is no constant to point at. Claude Code emits no rank over models. The names in
play today are Fable 5.1, Opus 5, Sonnet 5 and Haiku 4.5, each with full ids and
aliases beside it. A rank written into a hook is a copy of that list. CLAUDE.md says
a gate's allow list must point at the constant the code emits, never a copy of it. A
copied rank is also stale on the day a model ships.

A ceiling therefore does not belong in a hook. The owner ruled the same on
2026-09-28: the ceiling is prose only, and no forcing returns.

One constant does exist, and the repository already points at it. The fallback value
in `settings.json` is what the harness reads at entry 3. Guard rule 8 already keys on
that variable by name. Any test of the form "this write changes the fallback" needs
no rank at all.

## Question 3. The shape problem

Still unsolved. It no longer needs solving.

For an `Agent` call the model is now readable, because dropping the pin restores
entry 1 and the field survives to the payload. For a `Workflow` script that computes
`model` in a variable, a hook sees the script text and not the value the script will
produce. For a fork there is no model field to read. For a skill run in a subagent
with `model: inherit` there is none either. Both of those run the main conversation's
model and would escape any subagent gate, exactly as they escaped the pin.

A gate covering only the `Agent` shape would go quiet on the shapes that carry the
most model freedom. This repository already records that a guard people learn to
scroll past is spent, in `guard-that-cries-wolf-is-spent`. A guard that is silent
where it matters buys the same false confidence by the opposite route. Partial cover
here is not worth having.

## Question 4. Whether a gate is needed at all

No per-spawn gate. Three reasons, in order of weight.

An ask blocks the dispatch. CLAUDE.md says that once an objective is underway, nobody
reads until the owner returns. A fan-out of four lanes would stall on the first ask
and stay stalled for hours. The gate does not cost tokens. It costs the parallelism
the whole lane model exists to buy.

The gate prevents the cheap error. It fires on over-provisioning, which costs 2.5
times one lane. It is blind to under-provisioning, which costs a rework cycle of 25
to 60 minutes. Spending a blocking prompt on the smaller of two error costs is
backwards.

Coverage is partial by shape, per Question 3.

What a gate would catch that the alternatives miss: the spend before it happens. The
Stop guardrail reads the transcript after the turn, when a 40-minute lane has already
run and the tokens are gone. That is a real gap, and this entry accepts it. The spend
it lets through is one lane at 2.5 times cost.

What prose, the report and the guardrail catch that a gate misses: every shape,
including forks and workflow variables. The whole-session pattern, rather than one
call. And the choice to under-provision, which a ceiling gate never sees at all.

One gate stays. The settings-write ask, guard rule 8, fires on a write that changes
the fallback. A write is a standing change, not a dispatch. Asking there stalls
nothing mid-fan-out, and the owner is the person doing the write.

## Question 5. The default, and the shape of the rule

The default stays `sonnet`. Sonnet is the floor and the ceiling, and the ceiling is
prose only (see "The ceiling, ruled 2026-09-28"). The words in CLAUDE.md now read:

> Every agent runs Sonnet, and that needs no word. Sonnet is the floor: no agent runs
> Haiku. Sonnet is the ceiling: an agent runs Opus, or any model above Sonnet, only on
> my word, for the spawn I name.

The anchor `roles-workers-run-sonnet` stated the repealed pin. A stale anchor is a
lie that a future reader will grep. Three anchors replace it, because the parts
mechanize differently. `roles-sonnet-is-the-default` is a gate on `settings.json`.
`roles-sonnet-is-the-floor` is a guard on rule `subagent-model-floor`.
`roles-sonnet-is-the-ceiling` is unmechanized, by owner ruling.

## Question 6. What the orchestrator owes at dispatch time

The one line before dispatch is the right shape and the right order. The reason comes
before the choice, to an audience whose view is unknown. That is the condition Lerner
and Tetlock found to work, and it is the condition the deleted gate failed. Keep it.

It is not sufficient, for two reasons.

It names only the up direction. With the floor, no departure below Sonnet exists, so
the line is owed for a departure up. The line asks; the owner's word decides.

Nothing after the fact can read which tier ran. The report names every dispatch, but
not the model. A Done line for a lane should name the tier when the tier was not
Sonnet. That is a report-format change, and `lint/report_gate.py` cannot check it,
because nothing tells the gate what model a lane actually ran.

## Why a justification is still the wrong mechanism

This reasoning is unchanged, and it is why any replacement only asks.

`hooks/model_gate.py` ran as a `PreToolUse` hook on `Agent` and `Workflow` calls. It
read the model from the tool payload. Above Sonnet, it looked for a
`MODEL-JUSTIFICATION:` line in the prompt. With no line it denied the call. With a
line it asked the owner and quoted the reason.

The gate read the reason after the orchestrator had already chosen the model. A
reason written at that point does not change the choice. It defends the choice.
Lerner and Tetlock showed this in 1999 ("Accounting for the Effects of
Accountability", Psychological Bulletin 125, 255-275). When a person expects to
justify a decision that is already made, the reasons they give are defensive
bolstering, not reconsideration. Accountability improves judgement only when it comes
before the decision, and only when the audience's view is unknown. A 2017 study of
process accountability (Hoffmann, Gaissmaier and von Helversen, Judgment and Decision
Making 12(6), 627-641) found the same shape. A demand to justify the process changed
neither accuracy nor strategy. The gate asked for the wrong thing at the wrong time.
It produced one line of text and no better choice.

The gate also had a structural cost. It had to read a model id out of a payload it
could not always resolve. Each gap needed a new shape test, and each shape test added
a false ask. The four commits that built it each closed a bypass and opened a new
edge. Question 3 records that this cost is unchanged.

## The grant, after the drop

An Opus worker is enabled for one repository, on the owner's word in chat. The
orchestrator writes `.claude/settings.local.json`:

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus"
  },
  "_subagentCapUntil": "2026-09-23T00:00:00Z"
}
```

The force key is gone from this file and from `settings.json`. The earlier argument
for setting both keys, which covered either merge rule for `env`, has no subject
left.

The grant is weaker than it was, and that is correct. It raises the fallback. It does
not pin. An orchestrator that wants one Opus lane says so. On the owner's word, it can pass the
model on that one call instead. That is cheaper and narrower than a repository-wide
raise. The grant is for
the case where several lanes in a row need the higher tier.

That write triggers guard rule 8 when a file tool makes it. The ask names the model and the
file, so the raise never lands in silence. A shell write is not asked: `hooks/config_watch.py`
reverts it after the call (decisions/guard-trims-from-the-audit.md). `_subagentCapUntil` sits outside the `env` block, is read
only by `hooks/config_watch.py`, and must be no more than 24 hours ahead. A deadline
that is missing, unparseable, passed, or too far out gets the file reverted to the
`prior` content the watch holds. With no `prior` on record the watch reports the file
as UNKNOWN and asks the owner to read it by hand.

## What was measured

The findings below stand. Only their subject has narrowed.

A project-local `.claude/settings.local.json` overrides the user-settings value for
`CLAUDE_CODE_SUBAGENT_MODEL`, in a fresh process. The check ran `claude -p` from a
new terminal tab, with the grant file already in place. That process spawned a
subagent whose own `printenv` printed `opus`, twice, independently. The user settings
hold the default at `sonnet`, so only the project file could produce that reading.

A written grant does not apply to a session already running. A second subagent in the
same session still read `sonnet`. The grant needs a fresh session.

Guard rule 8 fires on the documented payload. Fed the exact write call, it returned
an ask naming the model and the file.

The force flag never appeared in a subagent's own shell under `printenv`. The harness
consumed it internally. That reading is now history rather than a live property.

MEASURED, on the expiry field's isolation: a cap reading taken over a line that holds
only `_subagentCapUntil` returns an empty mapping. The `PreToolUse` ask stays silent
on a write that touches only the deadline.

## What this changes

`settings.json`. Remove `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` from the `env` block. Keep
`CLAUDE_CODE_SUBAGENT_MODEL` at `sonnet`. Keep
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` at 1.

`CLAUDE.md`. Replace the ceiling sentence with the Sonnet floor-and-ceiling words in
Question 5, under three anchors in place of `roles-workers-run-sonnet`. Drop the force key from the
grant JSON in `roles-opus-override-guarded`. Reword `roles-opus-override-guarded` and
`roles-override-carries-expiry` from lifting a pin to raising a default, keeping both
anchors. Make `roles-opus-shaped-say-so` and the raise rules the only path to Opus, and only on
the owner's word.

`hooks/`. `hooks/guard.py` keeps rule 8 and keeps the optional `_FORCE` group, and adds
rule 9, `subagent-model-floor`. `hooks/config_watch.py` and
`hooks/test_config_watch.py` are untouched. No new hook file is added.

`lint/rule_mechanisms.json`. Drop the `roles-workers-run-sonnet` key. Add
`roles-sonnet-is-the-default`, as a gate on `settings.json` with the needle
`CLAUDE_CODE_SUBAGENT_MODEL`. Add `roles-sonnet-is-the-floor`, as a guard on rule
`subagent-model-floor`. Add `roles-sonnet-is-the-ceiling`, as `unmechanized`, with the
owner's ruling as reason. The entries for `roles-opus-override-guarded`,
`roles-override-carries-expiry` and `roles-remove-override-file` keep pointing at
guard rule `subagent-model-cap`.

## What stays uncovered, on purpose

A fork runs the main conversation's model, and so does a skill run in a subagent with
`model: inherit`. Nothing here touches either. The prose rule is the only guard on
them.

Over-provisioning of one lane, a spawn above Sonnet with no word from the owner,
passes without a prompt. Only prose forbids it, by owner ruling. The Stop guardrail
reads it after the turn. Question 4 accepts that gap and prices it.

Under-provisioning is caught by nothing before the rework cycle. That was also true
before the pin was dropped, and it is true again under the floor, which forbids
Haiku outright.

## Where this lives

This file keeps its slug name. No number is claimed on a branch.
