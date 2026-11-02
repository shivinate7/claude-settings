# Plan: three catalog plugins, add or skip

This plan assesses three plugins the owner named on 2026-11-01 21:32 CST: iceberg, Ambition
Lenses and Hypotize. It reads each plugin's own files, not only its README. Nothing was
installed and no setting changed. "Unknown" marks a fact no read confirmed.

## Verdicts

| Plugin | Verdict | Gold standard: one home per capability, no load on every task | Gap |
| --- | --- | --- | --- |
| iceberg | Skip | Prose has one home: `lint/ste_lint.py` and the fresh-prose skill | A second prose rulebook that tells Claude to rewrite every plan and doc |
| Ambition Lenses | Skip | Working rules have one home: the root `CLAUDE.md` | A second rulebook of about 2,000 words that a SessionStart hook loads into each task |
| Hypotize | Skip | A plugin serves work that this repo's sessions do | Growth-experiment tracking on an outside service. No session here does that work |

## Where each plugin was found

All three are in the claude.ai plugin catalog, in the marketplace "Anthropic Directory"
(`anthropic-plugin-directory`). Each has publisher tier `community`, basis `directory_review`.

- **Not from Anthropic.** The owner said iceberg is from Anthropic. The catalog lists it in
  Anthropic's directory, but its author is gagoar, a community author. Anthropic's own catalog,
  "Knowledge Work" (`anthropic_catalog`), holds none of the three.
- **Names.** "hypotize" is the plugin's real name. A plugin named "lens" (author Apurv Bazari)
  also matched. It is a different plugin and is not assessed here.
- **Sources read.** Each source was cloned into a scratch folder and only read.

| Plugin | Repo | Commit read | Version |
| --- | --- | --- | --- |
| iceberg | `gagoar/iceberg` | da7658d (2026-10-20) | 0.5.4 |
| Ambition Lenses | `JamesFincher/ambition-lenses` | 6ecb9cc (2026-10-14) | 1.1.1 |
| Hypotize | `hypotizeai/hypotize-plugin` | 4e0e743 (2026-10-22) | 1.1.2. The catalog lists 1.1.0 |

Searches run: `SearchPlugins` with iceberg, ambition lenses, hypotize, hypothesize and
hypothesis; three web searches; and `gh api search/repositories` for each name.

Cloud load is unknown. Decision `adoptions-declined-2026-09-28` (adoptions the owner declined)
says cloud sessions load no plugins from local settings. Whether a catalog plugin loads in a cloud
session was not tested.

## iceberg

**What it adds.** Three skills: `edit`, `score` and `jargon`. Two agents: `iceberg-edit`
(Sonnet) rewrites a document, and `iceberg-score` (Haiku) grades it against 14 writing rules.
One `Stop` hook.

**Cost.**

- Context: three skill descriptions at each session start, about 450 words. The skill bodies,
  about 480 lines, load only when a skill runs.
- The `Stop` hook runs one shell and `jq` at each turn end. If `.iceberg/last-score.txt` exists,
  the hook adds its first 2,000 characters to the turn's system message.
- The skills and agents write `.iceberg/` in the working folder of each repo.
- It uses no network and no secrets. The hook needs `jq`.

**What it says in its own files.** The `score` and `edit` skill descriptions say: "ALWAYS run
automatically on every plan Claude produces ... This is not optional and requires no user
prompt." So the model would grade and rewrite each plan and doc it writes, and spawn an agent
for each doc over 500 words.

**Overlap.**

- Rule `output-write-in-ste` (write plainly) and decision `plain-prose-lint` (the STE lint is a
  plain-prose lint). Home: `lint/ste_lint.py`, `lint/ste_gate.py`.
- Skill `fresh-prose` (prose that stays true).
- Output style `shiv-stylisms` (short and plain replies).
- Hook `prose_judge.py` (judges prose edits in decision records).
- Its Rule 17, "strip AI commentary", overlaps rule `building-comments-say-why` and
  `lint/check_comment_narration.py`.
- Its jargon list overlaps rule `speak-cite-id-plus-gloss` and `GLOSSARY.md`.

**Rules it fights.**

- `building-one-home-per-capability`: a second prose rulebook. Some of its rules differ from
  ours, for example Rule 9, "use you", and Rule 11, "no negative framing".
- `roles-brief-contents` (what a brief holds): its "always automatically" trigger spawns agents
  with no brief from the orchestrator.
- `verification-cry-wolf-guard-is-spent` (a false alarm is spent): the `Stop` hook repeats the
  last score at every turn end, after that score is out of date.
- `shared-trees-own-ports-data` (each checkout its own data): it writes `.iceberg/` into each
  repo's tree.

**Verdict: skip.**

- Gain if added: a graded report per document, with quoted faults.
- Loss if added: a second prose home with rules that differ from ours, a rewrite of each plan
  with no ask, and an untracked folder in each repo.
- Note: two of its rules could become lookup rules in `lint/ste_lint.py`: Rule 7 (condition
  before instruction) and Rule 14 (a number instead of "fast" or "large"). That is a separate
  lane, on the owner's grant.

## Ambition Lenses

**What it adds.** One skill, `ambition-lenses`, and one `SessionStart` hook. The skill body is
1,978 words. Two reference files add 1,461 words, read on demand.

**Cost.**

- The hook runs `cat` one time per session start. It prints: "Before starting any substantive
  task ..., invoke the ambition-lenses skill with the Skill tool and apply it for the whole task."
- So the skill body loads into nearly every task, about 2,000 words. Its token count is
  unmeasured.
- It uses no network and no secrets.

**Overlap.** Most of its failure-mode table is a rule here already.

| Its countermeasure | Our rule |
| --- | --- |
| Altitude: the outcome the task serves | `outcomes-judge-by-outcome` |
| Plausibility over truth: verify against the source | `building-never-guess-answer`, `verification-report-unknown-reads` |
| Premature "done": define done as a check | `roles-brief-contents`, `roles-each-layer-proves-once` |
| Grading your own work: use a fresh reviewer | `roles-one-role-per-agent`, the reviewer agent |
| Context decay: re-read files | `verification-verify-against-repo`, `tokens-never-load-whole-doc` |
| Fix the cause | `building-fix-cause-not-symptom` |
| Never weaken a test | `roles-review-cap-three`, `outcomes-tests-are-statements` |

**Where it differs from our rules.**

- `building-one-home-per-capability`: a second set of working rules, loaded beside the root
  `CLAUDE.md`.
- `roles-one-role-per-agent`: its Range step has one agent do the work of a red team, a skeptic
  and other roles.
- Scope. Its Altitude step asks for "a version that also solves the next three requests". But
  its Execute section (`SKILL.md` lines 90 to 93) says: "Do the task that was asked", "Offer
  what's expensive ... Don't build the bigger thing unasked", and "Fold in what's cheap ...
  without changing scope". So it offers the bigger version and does not build it. The real
  difference from rule `outcomes-grant-covers-named-act` (a grant covers only the act it names)
  is small extra acts it folds in with no ask: "handle the edge case, add the test".

### Outcomes compared on real cases

The owner asked (2026-11-01 22:27 CST) which gives the better outcome: our rule and guard, or the
plugin's prose. These are the cases the evidence holds.

What the evidence lacks:

- Rule `outcomes-grant-covers-named-act` has no guard. It is a judgment rule:
  `lint/rule_mechanisms.json` line 28 says "No hook parses an instruction and an action for a
  match". So no guard refusal of it exists to count.
- `~/.claude/guard.log` in this cloud container holds 8 rows, all from this session. None cites
  that rule.
- `~/.claude/handoffs` is absent here. Session transcripts are on the owner's computer. Both are
  unknown.
- So the cases come from the incident records in `docs/decisions/`. Each is one owner
  correction. The rework each caused is unknown. The plugin's column is a reading of its text,
  not a run.

| Case (source) | Our outcome | Plugin outcome, read from its text | Better | Gold standard |
| --- | --- | --- | --- | --- |
| Duo port invented an "end of mail day" and asked a question the web app answers (`port-keeps-behaviour` line 37, 2026-10-27) | Owner corrected it. Then a rule and a check, landed 2026-10-28 | Its "plausibility over truth" row says verify against the source. Its Altitude step invites a redesign | Tie. Both read the source; ours is a guard, theirs is prose | The port copies the app's behaviour; no question the code answers |
| Orchestrator asked to merge under a standing merge grant (`port-keeps-behaviour` line 38, 2026-10-27) | Owner corrected it. Rule: read CLAUDE.md for grants first | No text on grants | Ours | No ask that a grant answers |
| A question on CI internals the owner could not judge (`owner-judge-test` line 24, 2026-10-28) | Owner saved an answer with "i really can't figure out how to decide". Then a rule | "Fold in what's cheap ... just do it": the session takes the pick | Plugin, before our rule; tie after it | No question the owner cannot judge |
| A waiting item proposed loosening a shared tool for one repo (`uniform-over-variants` line 20, 2026-10-27) | Owner ruled: the repo changes, never the tool | "A durable workflow" could argue either way | Unknown | One format, no per-repo exception |
| An orchestrator started four sessions, and the owner had to accept each (`lanes-start-as-agents` line 25, 2026-10-26) | Then a check | "Parallelize what's independent" pushes the same act | Ours | No owner click for work he asked to run |
| A lane's question restated main (`port-keeps-behaviour` line 39, 2026-10-30) | Then a check on the question form | No text on it | Ours | No question that restates main |

Score on these six: ours better 3, plugin better 1 (before our rule), tie 1, unknown 1. No case
shows the plugin building an unasked act. No case shows our rule causing work the owner later had
to ask for. Six records is too few to rank either side with confidence.

**Cost against gain.**

- The plugin loads 1,978 words into each substantive task, plus 30 words from its hook.
- Its failure-mode table is 408 words. The ten rules of ours it repeats total 297 words. They
  load already in the root `CLAUDE.md` (3,973 words).
- So about 1,570 words per task are new: its creed, its four roles, its scaling notes and its
  loop. No case above turns on those words.

**Verdict: skip the install.**

- Gain if added: one case in six, a question the owner could not judge, goes better. Our rule
  `questions-go-to-owner` now covers that case.
- Loss if added: about 1,570 new words per task. A push to parallelize that one case shows as
  harm. It also sets a second home for working rules.
- What would change the verdict: a trial. Run the same briefs with and without the skill and
  count owner corrections and unasked acts. That needs the owner's grant and transcripts from his
  computer.

## Hypotize

**What it adds.** Three skills: `hypotize-backlog-import`, `hypotize-growth-experiments` and
`hypotize-weekly-review`. One remote MCP server at `https://api.hypotize.ai/mcp` (HTTP). No hooks
and no agents.

**Cost.**

- Context: three skill descriptions at each session start. The bodies, 3,399 words in total,
  load only when a skill runs. The MCP tool list loads once the server is connected.
- Network: each tool call goes to `api.hypotize.ai`, an outside service.
- Secrets: an account on that service, through sign-in with Google or email.
- Delete tools exist only if the user grants the `hypotize:delete` scope at sign-in. The default
  is off.

**What it does.** It tracks growth experiments for product and marketing teams: a scored
backlog, a fixed lifecycle from idea to outcome, and a library of learnings. It does not run A/B
tests.

**Overlap.** None with this repo. The roadmap and waiting-page skills track repo work and the
owner's questions, not growth experiments.

**Rules it fights.** No hook rule. It has no agents, so `agent-model-cap` (model per role)
does not apply. It sends work data to an outside service. Whether the
owner's employer allows that service is unknown. Whether any repo of the owner's runs growth
experiments is unknown.

**Verdict: skip for claude-settings.**

- Gain if added: a record of growth experiments that Claude can read and write.
- Loss if added: an outside account and data on an outside service, for work no session here
  does.
- If the owner runs growth experiments for a product, he adds it to his own account from the
  catalog, outside this repo.

## Owner question

The coordinator brings the three verdicts to the owner as one question. Adding any plugin needs
his word.
