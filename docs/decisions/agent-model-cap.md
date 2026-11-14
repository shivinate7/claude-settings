# Agent model cap

## The ruling

Each agent role runs the model and effort of its row in the table below. Sonnet is the ceiling.
Opus runs only for Plan, the built-in advisor (`advisorModel`; agents inherit it), the designer and the design reviewer (owner, 2026-10-26, waiting-page item 15, "b"; decision `design-agents`), and the builder's third try by standing grant,
and the owner watches that cost. The refuter runs Opus too (owner, 2026-11-06 12:43 CST, waiting-page item 279, pick d; decision `plan-refuter`). An Explore may run Sonnet or Opus when its brief's first non-blank line carries the `Audit:` marker
(owner, 2026-11-01 18:38 CST, waiting-page item 137, pick a). An Explore on Opus with no marker is refused, and an override lifts it; no scoped `opus explore` form exists (option b, not picked).
The question reviewer agent hook keeps its class-level grant of 2026-10-21 (see its row). Any other spawn above its role's model, a reviewer's round 3 on Opus too, is refused. It runs only when the owner's typed override or grant names it
(owner, 2026-11-01 17:25 CST, item 127, pick a: the same for Sonnet and Opus). A lane, an arbiter, a coordinator, a triage or a batch runner is a session, not an agent: it runs the model of its row below. A review round runs the model of its round row (see the round rows). Haiku runs only in Explore,
claude-code-guide, test-author, reviewer and record-writer. The guard enforces the ceiling and the role rows. An Agent
or Task spawn that sets model opus is refused, unless Plan, designer, design-reviewer, refuter, a builder's `Round 3 of 3` or an Explore's `Audit:` marker covers it.
The general override lifts any refusal of a spawn above its role's row. An Opus spawn refusal is also lifted by `opus [role] <time>` (for example `opus 2h` or `opus builders 2h`), by the owner's plain Opus ask in his own typed prompt (owner, 2026-11-03 19:47 CST, chat; the override decision `owner-override`, The Opus override), or by a step grant.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped and stays dropped.

The default: `env.CLAUDE_CODE_SUBAGENT_MODEL` is `sonnet` in `settings.json`,
`env.CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` equals it, and `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1.
The ask on a settings write and the expiry of a grant are in `opus-grant-expires`, an Opus grant expires.

**The model per role.** Reason: Haiku is cheap enough for read-only work, tests, review and
record-writing, and the owner will measure cost and quality. Writing prose and records is not building.

| Point | Model | Effort |
|---|---|---|
| `CLAUDE_CODE_SUBAGENT_MODEL` | sonnet | n/a |
| Explore, claude-code-guide | haiku | xhigh |
| Explore that audits or judges meaning, not a plain search | sonnet or opus, when its brief's first non-blank line carries the `Audit:` marker (owner, 2026-11-01 18:38 CST, item 137, pick a); set per spawn, which overrides the frontmatter `haiku` | high |
| test-author | haiku | xhigh |
| reviewer | haiku | xhigh |
| reviewer, per round (the round rows below) | the round rows: haiku on a round 1 of a change with no guard or check, sonnet from round 2, on a guard or check change, and on a fix verifier; set per spawn, which overrides the frontmatter `haiku` | the round rows |
| record-writer (`agents/record-writer.md`) | haiku | xhigh |
| builder | sonnet | high |
| builder, try 3 after a FAIL at review round 2 | the round rows: opus, the owner's standing grant; set per spawn, which overrides `CLAUDE_CODE_SUBAGENT_MODEL` | the round rows |
| Plan (`agents/plan.md`) | opus | high |
| designer (`agents/designer.md`) | opus, the owner's standing grant of 2026-10-26 | high |
| design-reviewer (`agents/design-reviewer.md`) | opus, the owner's standing grant of 2026-10-26 | high |
| refuter (`agents/refuter.md`) | opus, the owner's ruling of 2026-11-06 12:43 CST, waiting-page item 279, pick d (decision `plan-refuter`) | high |
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
| coordinator, standing session (decision `session-tiers`; overrides the separate-sessions row below) | opus, the owner's ruling of 2026-11-11 13:52 CST (R33, "all three stay on opus for now until 3.7"); stays on Opus after R52 | not ruled; model default |
| triage, standing session (decision `session-tiers`; overrides the separate-sessions row below) | opus, the owner's ruling of 2026-11-11 13:52 CST (R33); stays on Opus after R52 | not ruled; model default |
| batch runner, in this repo and in child repos (decision `session-tiers`; overrides the separate-sessions row below) | claude-sonnet-5-5, the owner's ruling of 2026-11-12 13:07 CST (R52), which ends his Opus hold of 2026-11-11 13:52 CST for this role only; it becomes the default when its batches show no wrong drop, no wrong merge and no stalled batch against the Opus runs before it | medium, the owner's ruling of 2026-11-12 13:07 CST (R52) |
| separate sessions (`start_session`, `create_session`) | main model unless the owner names one | default |
| lane (decision `session-tiers`) | sonnet (temporary), the owner's ruling of 2026-11-08 12:21 CST, waiting-page item 439 (lane-model-sonnet), pick none; debt `lane-model-recheck` rechecks it | medium, the owner's ruling of 2026-11-10 13:19 CST; set by the start's effort field, below |
| arbiter session (decision `session-tiers`) | opus, the owner's ruling of 2026-10-29 16:42 CDT, waiting item 81, pick a | high |
| safety-classifier fallback | on, the default | n/a |
| Agent spawn judge (`hooks/call_judge.py`, PreToolUse on Agent, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| prose judge (`hooks/prose_judge.py`, PreToolUse on Edit and Write; a model call only for a path with a `decisions` folder segment) | haiku, through `decision_watch.invoke_model` | xhigh |
| reply judge (`hooks/reply_judge.py`, Stop) | haiku, through `decision_watch.invoke_model` | xhigh |
| report guard past-ruling check (`lint/report_guard.py`, Stop) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| feedback guard (`hooks/feedback_guard.py`, Stop; one call per Stop that has a new inbox item and an older item to compare with) | claude-haiku-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| question reviewer (the same script, on AskUserQuestion and on an ArtifactData write of a waiting-page item) | claude-opus-5-5, through `decision_watch.invoke_model`, by the owner's standing grant of 2026-10-21, given at class level for this hook (decision `question-reviewer-agent-hook`) | model default: the call passes no effort |
| SendMessage busy judge (`hooks/sendmessage_state.py`, PreToolUse; a model call only when the receiver is busy on the session board) | haiku, through `decision_watch.invoke_model` | xhigh |
| SendMessage wording judge (the same script, one call on every send, so an override can lift it) | claude-sonnet-5-5, through `decision_watch.invoke_model` | model default: the call passes no effort |
| plain-diff mod note (`mods/plain-diff/hooks/register.mjs`, `$.model.complete`, one call per file with no note) | haiku, set in the call | none set: the call passes no effort field |
| decision watch (`hooks/decision_watch.py`) | haiku | xhigh |
| decision watch mod (`mods/decision-watch`, the Stop-time judge) | haiku, through `$.model.complete`, the app login; the python path above stays xhigh | session default: the call passes no effort field |
| every other hook and guard | no model; plain code | n/a |
| local_time (`hooks/local_time.py`, UserPromptSubmit only; a model call only for a plain owner ask with the whole word `override` or `opus` that passes its gates, plus one scope read after a yes, for an opus ask that names no role and has an earlier prompt; a failed plain ask grants nothing; a first-word `override` with a reason still grants a one-act override) | haiku, through `decision_watch.invoke_model` | low |

**The round rows.** The one home of the model and effort of each review round and of the builder's third try. The guard (`role_round_table` in `hooks/guard.py`, beside `role_model_table`) and the merge tool (`--round`, `--fix-check`) read these rows, so a changed row changes their verdicts with no code edit. A `Round` cell is a round number, `1 guard` or `1 other` for round 1, or `fix verifier`. A round 1 brief that starts a line with `Guard or check: yes` (`REVIEW_GUARD_MARKER` in `hooks/shared_names.py`, the guard marker) takes the `1 guard` row, any other round 1 brief the `1 other` row. A reviewer brief for round 2 or 3 opens its first line with `Round N of 3`; a fix verifier's first non-blank line starts with `Fix check`. A round with no row, or a row naming a model the guard cannot rank, falls back to `ROLE_ROUND_FALLBACK` in `hooks/guard.py`. That table gives sonnet for a reviewer's `1 guard`, round 2, round 3 and `fix verifier`, and opus for the builder's round 3. It has no row for a reviewer's `1 other`, so the role row (haiku) applies. `lint/check_agent_models.py` fails a row whose model the guard cannot rank.

| Role | Round | Model | Effort |
|---|---|---|---|
| reviewer | 1 guard | sonnet | xhigh |
| reviewer | 1 other | haiku | xhigh |
| reviewer | 2 | sonnet | high |
| reviewer | 3 | sonnet | xhigh |
| reviewer | fix verifier | sonnet | xhigh |
| builder | 3 | opus | high |

Reasons and rulings. Round 1 on a guard or check diff runs Sonnet (owner R9, item 359 a, Nov 10 15:44 CST). A fix verifier runs Sonnet on every PR (owner item 444 a, 2026-11-08 15:04 CST); the merge tool refuses a record that names another model. Round 2 on opus: the step-up refuses it, and no override lifts that. Round 3 on opus: the Opus ceiling refuses it, and the owner's typed override lifts it (2026-11-01 17:25 CST, item 127, pick a). Round 2 effort is set per spawn; the other reviewer rows take the frontmatter's xhigh. The builder's third try runs Opus by the owner's standing grant.

The Agent prompt judge refuses an audit Explore (a brief that asks it to audit, review, judge, rate or
compare meaning) unless the call sets model sonnet or opus; haiku or no model refuses. Explore stays a
Haiku role, so Sonnet is the floor for the judge only. An audit Explore on Sonnet also carries the `Audit:` first-line marker, or guard rule `agent-role-model` refuses it. An audit Explore on Opus carries the same marker
(owner, 2026-11-01 18:38 CST, item 137, pick a), or guard rule `agent-model-cap` refuses it, and an override lifts that; the judge passes it. A plain search passes on the Haiku default. The caller
spot-checks findings before it acts on an audit.

`lint/check_skill_model_rows.py` fails CI when a skill under `skills/` has no row, or a row names a
missing skill. A skill's model is the model of the session that calls it.

Reason the ceiling is a refusal and no ask (owner, 2026-11-01 17:25 CST, item 127, pick a): Claude Code emits no rank over models, and a permission prompt cannot time out, so an ask stalled a fan-out. A refusal names the owner's typed override, which lifts it. The role row below refuses a rank above the row. It ranks the three aliases `haiku`, `sonnet` and `opus` by substring, as the floor does. It reads each row live from this record, so it holds no copy of the table.

**The floor.** Every role but the five Haiku roles has Sonnet as the floor. `HAIKU_ROLES` in
`hooks/guard.py` is the one list. Guard rule `agent-model-floor` refuses an `Agent`, `Task`, `Workflow`
`agent()`, `start_session` or `create_session` call whose `model` holds "haiku", unless the role is a Haiku role.
`lint/check_agent_models.py` fails a Haiku `model:` in `agents/*.md` or `skills/*/SKILL.md` frontmatter,
unless the file is a Haiku role. It also fails an `agents/*.md` body that states the agent's own model in fixed text, or whose report header has a `<model>` slot and no `powered by the model named` line. The spawn's model reaches the agent through its system prompt, so a body names that line as the source. `agents/plan.md` pins Plan.

**The role row.** Guard rule `agent-role-model` reads this table at each `Agent` or `Task` spawn, from the pointer checkout (the one `~/.claude/CLAUDE.md` names; `role_model_table` in `hooks/guard.py` is the one reader). A row names a role in its first cell and a model in the first word of its second cell. A first cell that holds more than role words (a qualifier such as `reviewer, rounds 2 and 3`, a skill, a hook) names no role, and the first row for a role wins.
- A spawn that names a model above its role's row is refused, with the remedy "drop the model field, or name the role's model". A reviewer's refusal also names the brief forms that lift a reviewer above its row, as the round rows set them (the `Round N of 3` marker for the rounds whose row is above the reviewer's row, the guard marker, the fix check marker). The general override lifts this refusal (owner, 2026-11-01 17:25 CST, item 127, pick a). Ranks run haiku, sonnet, opus. A model with no rank counts as above every row below opus, so it is refused there; its own rank is unruled. The merge tool's `--review-record` refuses a reviewer round 2 or 3 (`--round N:..`) whose model is not its round row's. It allows round 3 on opus, or a granted round 4 (`--grant`). The record takes no override. A role with no row passes. A role matches its row without case and without surrounding space.
- Exempt: an `Agent` or `Task` Explore spawn whose brief's first non-blank line carries the audit marker `Audit:` (`EXPLORE_AUDIT_MARKER` in `hooks/shared_names.py`, which the guard and the spawn judge both import; case-sensitive, the first `Audit:` on the brief's first non-blank line, with any text ahead of it, so `**Audit:**` counts; the same first-line pick as the step-up marker scan). Any other such Explore that names a model runs on its haiku row. The guard passes an Explore that names no model whenever `CLAUDE_CODE_SUBAGENT_MODEL` is set (`agents/explore.md` pins haiku, so it also passes without the variable; see the no-model bullet). A Workflow `agent()` call that names a model is judged the same way, by its `agentType` and the brief it passes. A brief the scan cannot read (a variable, or a prompt key beside a spread) carries no marker, so the call is judged with an empty brief, and its refusal adds "write the brief as a literal string so the marker is readable" (item 127 pick a; coordinator ruling, 2026-11-01 22:54 CST). A call whose `model` or `agentType` the scan cannot read (a variable, a shorthand, or a spread with no literal `agentType`) is skipped. Owner ruling: shiv, 2026-11-01 11:43 CST, waiting-page item 107, pick a. The refusal names the marker. Also exempt: a reviewer whose brief holds a `Round 2 of 3` or `Round 3 of 3` marker (the same marker scan as the step-up), and every Opus spawn, which the ceiling above judges (an Explore on Opus needs the marker there too, item 137 pick a). A reviewer whose brief's first non-blank line starts with the fix check marker `Fix check` is exempt too, to Sonnet only, on every PR (owner item 444 a, 2026-11-08 15:04 CST; `FIX_CHECK_MARKER` in `hooks/shared_names.py`; case-sensitive; blanks may stand ahead of it, text may not; the refusal names it). A reviewer whose brief carries the guard marker is exempt to its `1 guard` row's model on any round (owner, item 359 pick a, 2026-11-07 14:41 CST). A reviewer's round 1 with no guard marker runs its `1 other` row.
- A spawn that names no model is refused under two conditions. `CLAUDE_CODE_SUBAGENT_MODEL` is unset or empty in the guard's environment. No `agents/*.md` file in the pointer checkout names the role with a `model:` pin in its frontmatter. A spawn with no role counts as general-purpose. The remedy is "name the role's model", with the row's model beside it unless the row is haiku.
- With no pointer checkout the rule stands down and logs nothing. A table or agents folder in the pointer checkout that cannot be read passes the spawn and logs one `agent-role-model-unread` line, which `lint/guard_log_report.py` counts as a note for that rule.
- The override lifts an above-row refusal (owner, 2026-11-01 17:25 CST, item 127, pick a; `never_lifted` in `hooks/guard.py` no longer reads it). No override lifts the no-model refusal (`owner-override`, the model guards).

Cost: one read of this record per spawn (unmeasured). A spawn with no model adds one read of the agent files (unmeasured). No process starts, and no file is written but the unread line. Kind of risk: incident. Landed 2026-10-30.

Incident one: briefs named sonnet for haiku-row roles until 13:59 CDT on 2026-10-30. Incident two: the round-2 builder of PR 872 named no model. The cloud CLI had no `CLAUDE_CODE_SUBAGENT_MODEL`, and `agents/builder.md` has no pin, so it inherited the lane's Opus (note `nao-builder-ran-opus`).

**The lane effort pin.** A lane runs at medium effort (owner, 2026-11-10 13:19 CST, "B is good").
The coordinator starts a lane with `create_session` set to effort `medium`, with `model` (the lane row's)
and `source_url` (the repo), and with its whole brief as the first prompt. The brief opens with a Grant
line, `Grant: <owner words>, <time>`. The lane treats it as the owner's grant. It checks the grant against
the coordinator's chat only when the act cannot be undone (coordinator, 2026-11-10 13:18 CST). The effort
comes from the field, because a slash command runs only as the whole prompt (measured by the
coordinator's probe, 2026-10-30 15:26 CDT: that prompt set `effort_level` medium; the same line with text
after it set none). Guard rule `lane-effort-pin` (likely risk, first landed 2026-10-30) refuses a `create_session`
call tagged `cs-build:lane` unless its `effort` is `medium` and its prompt's first non-blank line is a Grant line
with owner words after it. Owner words hold a letter or digit and no `<`, so a placeholder Grant such as
`<owner words>` is refused. Rule `lane-one-topic` also reads a lane `create_session` prompt. When the prompt's
`Lane brief:` line follows the Grant line, its Topic must match the call's `cs-topic` tag. A `send_message`
brief follows the same rule (owner chat, 2026-11-10 13:19 CST, "B is good", page item 495 a). A lane
started with no `cs-build:lane` tag is unseen; the
tag is the coordinator's rule in `session-tiers`. An owner override lifts it; it is not one of the role and model guards
that `owner-override` keeps beyond every override (owner, 2026-10-30 16:25 CDT, in chat to lane-effort-medium (session_013NEJL28Sky6HBLLehmziKH), pick a: liftable). `LANE_EFFORT` in `hooks/guard.py` is the one
value; `lint/check_agent_models.py` fails when the lane row's effort cell does not start with it.
The session roles that set an effort are the lane, the batch runner and the arbiter; the others keep the model default. Ruled out: `effortLevel` in user settings does not count for Opus
5.5, project settings and an environment's `CLAUDE_CODE_EFFORT_LEVEL` reach every tier, and a
SessionStart hook reaches only Bash.

**The lane repo tag.** Guard rule `lane-repo-tag` refuses a `create_session` call tagged `cs-build:lane` that
carries no tag equal to `cs-repo:` plus the calling checkout's GitHub `owner/name`. The tag is read as the
roadmap reads it (`repo_tag_names` in `hooks/shared_names.py`, which both import): the exact prefix, no strip,
the owner/name compared without case. A tag the roadmap cannot read does not pass the guard. The repo is read
as the roadmap build reads it (`github_repo` in `hooks/git_reads.py`, which both call). The `github` key of the
`roadmap` object in the layout extras file comes first. Else the repo is the last two segments of the origin's
path, with `.git` stripped. The host is never read, since the cloud proxy serves another host. An https, scp, or ssh origin with
a port counts, and a local path with no scheme counts by its path. With no readable repo, any
`cs-repo:<owner>/<name>` tag passes. The deny reason names the tag to add. A roll-out lane carries this repo's
tag beside its target's. The rule runs after `lane-effort-pin`, so a call that breaks both reads the pin
first. An owner override lifts it.
The roadmap build shares this read (`github_slug` and `blob_url` in `skills/roadmap/build.py`). For an ssh origin with a port, a non-GitHub https origin or a POSIX local path, the build links its last two path segments on github.com.
Cost, per lane `create_session` only: one extras file read, and one `git remote get-url origin` process start
when the extras name no repo (unmeasured). A deny writes one guard.log line (unmeasured). No other file, and no timer.
Known gaps: a Windows drive path with backslashes reads as no origin. A `cwd` below the repo root reads no
extras file. Tags set by `set_session_tags` after the start are not judged.
Kind of risk: incident. Landed 2026-11-01.

Incident: 2026-11-01 18:08 CST, lanes tagged with the short repo name made 18 false in-progress flags on
the roadmap page, because the live check matches the full tag.

**The lane start settings.** Guard rule `lane-start-settings` refuses a `create_session` call tagged `cs-build:lane`
whose input has no `model` or no `source_url`; an empty or whitespace-only value counts as missing. A lane with no
repo has nothing to work in. A lane with no model starts on the coordinator's model, not the lane row's. The coordinator
passes both on every lane start. The rule runs after `lane-repo-tag`. An owner override lifts it.
Known gaps: a lane tag set after the start is not judged, and `start_session` is not judged (both inherited from the
lane effort pin and the lane repo tag). Only `create_session` tagged `cs-build:lane` is a lane start to the guard,
because `start_session` carries no tags field. Mac lanes start by `start_session` (decision `lanes-start-as-agents`),
so they pass this rule unjudged; the owner decides whether to judge them. The rule checks that a model is present, not
which model.
Kind of risk: likely. Landed 2026-11-08.

**The lane title.** Guard rule `lane-title-slug` refuses a `create_session` call tagged `cs-build:lane` whose `title`
does not open with `Lane <branch slug>:` (`LANE_TITLE_FORM` in `hooks/shared_names.py`). The form is the word `Lane`, a slug of
lower-case letters and digits joined by single hyphens, and a colon. A missing, empty or placeholder title (`Lane <branch
slug>: <task>`) is refused. The deny reason prints `LANE_TITLE_FORM`; `LANE_TITLE_OPENING` is cut from that same string, so one source feeds the remedy and the check.
The rule runs after `lane-start-settings`. An owner override lifts it. Outcome: the owner reads a lane's branch in his
session list (rule `git-slug-then-claim-number`, name a lane by its branch slug). Lane start text: `templates/brief.md`
and `templates/operating-model.md` in skill `project-ops`. Known gaps: the rule reads the form, not that the slug is the
lane's real branch. A title set after the start is not judged. `start_session` has no tags, so no call of it is a lane
start and none is judged.
Kind of risk: likely.

**The step-up.** Guard rule `roles-third-round-steps-up` reads the `Round N of 3` marker in
the brief. A line that starts with it counts. When the brief's first non-blank line starts with no marker, the
leftmost marker on that line also counts if it is `Round N of 3`, such as "Builder, Round 3 of 3. Lane ...". A
leftmost `Try N of 3` there adds nothing. Owner ruling 2026-10-29 16:29 CDT: a round-3
builder on Opus just runs, with no approval. The first-line form is case-sensitive. Later lines count only
when they start with the marker. A builder's old `Try 3 of 3` still counts until note `try-marker-sunset`. A round 2 reviewer runs on Sonnet. A round 3 reviewer runs Sonnet; its refusal names Sonnet only, and Opus needs the owner's override (2026-11-01 17:25 CST, item 127, pick a). A try 3 builder needs Opus.

**No pin, and the ceiling is a refusal.** The variable is a true fallback: it decides only the spawns that name no
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
runs Haiku even where the variable is `sonnet`; rounds 2 and 3 and a fix check must set the model per spawn
(owner, item 444 a, 2026-11-08 15:04 CST).
A running cloud thread does not load `~/.claude/agents` files written mid-session: its Agent tool
refused `reviewer`, `designer` and `builder` as unknown types. A process started after the write
loaded all of them. Unknown: whether the cloud thread harness itself, as against a headless run in
the same container, reads the same order.

**The install's first home is the cloud environment's setup script** (owner, 2026-10-30 15:09 CDT,
waiting item 77, pick a). The setup script runs `cloud-setup.sh` before Claude Code starts, so
`agents/*.md` and `settings.json` are in `~/.claude` before the first agent spawn. The second home is
the SessionStart refresh hook that install.sh writes. It refreshes the files, but it runs too late for
the first spawn: a builder with no pin then ran Opus. The setup script cannot read the environment's
saved variables or secrets. So `cloud-setup.sh` fetches the public file first, and then copies from a
checkout of this repo that the environment attached. It always exits 0 and prints one verdict line.
The owner pastes the setup-script text once per environment; the text is in the README, under Cloud
sessions. Until an environment has it, the caller names model sonnet on each builder spawn there,
because `settings.json` with the variable lands only with the install. The setup script runs when a new
session starts (the environment's docs); whether it runs again on resume is unmeasured. Also unmeasured: whether the environment's repositories are cloned before the
setup script runs; the private-repo fallback needs that. Unmeasured too: whether the harness accepts
the session's checkout after install.sh moves it to main during setup. Test `hooks/test_cloud_setup.sh`
proves exit 0 and the install offline.

The guard holds the ceiling by a refusal (owner, 2026-11-01 17:25 CST, item 127, pick a: any spawn above its role's
model is refused, and the owner's typed override lifts it, the same for Sonnet and Opus; before that it was an ask
under the 2026-10-21 grant). An Agent or Task spawn that sets model opus is refused under
`agent-model-cap`, unless a standing grant covers it. A standing grant is one of: the role Plan, the role designer or
design-reviewer (the 2026-10-26 grant above), a builder with the `Round 3 of 3` marker (the step-up names the forms), or an Explore with the `Audit:` marker. It sits on its brief's first non-blank line (owner, 2026-11-01 18:38 CST, item 137, pick a). A reviewer's round 3 is no standing grant, so
it is refused. An override, `opus 2h`, `opus <role> 2h`, the owner's plain Opus ask (decision `owner-override`) or a step grant lifts the spawn refusal. The ask on a settings write under the same
id stays outside every override. The refusal fires only on an Opus spawn, so it stops a fan-out only where Opus was
asked for. A justification line is written after the model is chosen, so it defends the choice; the one line
before dispatch (`roles-opus-shaped-say-so`) names the reason before the choice, so it stays. The ask on a
write that changes the fallback stays: a write is a standing change, not a dispatch. The Opus refusal and the role row read
Agent and Task calls, and each Workflow `agent()` call whose `agentType` and model are string literals (the same static
scan as the Haiku floor and the step-up). Item 127 pick a and the coordinator ruling of 2026-11-01 22:54 CST rule that
a variable brief, or a prompt key beside a spread, grants nothing. It is judged as an empty brief. The override or a literal
brief lifts the refusal. A call whose model or `agentType` the scan cannot read is skipped. The floor reads the model, and the role only to exempt
a Haiku role. The step-up skips an unread brief. A Workflow `agent()` call that sets its model through a variable is unseen by all four
checks. A call that names no model is unseen by the floor and the Opus ceiling. The step-up still judges it: a builder
brief with `Round 3 of 3` is refused. The role row refuses it on an Agent or Task call only, when the role's agent file
pins no model (`floor-workflow-runtime-models`, `model-ceiling-no-after-read`). The refusal never reads a `start_session` on Opus.

A step grant also lifts the Opus spawn refusal (owner, 2026-10-29 13:44 CDT: grants live in the roadmap).
Triage writes the owner's grant in the `grants` field of the lane's roadmap step. The step names its
lane in the field `lane`. `take()` in `hooks/override.py` reads it only on an Opus spawn refusal that no Opus
override lifted. It reads the ref `origin/roadmap` in the call's cwd, and first fetches it through `lint/roadmap_ref.py`
when the roadmap's last fetch is older than 60 seconds, bounded at 2 seconds. Cost: one `git grep` for the lane id,
and one `git show` for each hit, plus, when the ref is stale, at most one `git fetch`. Freshness: a grant on origin lifts the
refusal at the next spawn; a fetch that fails reads the ref as it is, and a `noted` entry "step grant read as of
<time>" goes to guard.log. Kind of risk: likely. Landed 2026-10-29. Incident:
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
Home: cloud-setup.sh
