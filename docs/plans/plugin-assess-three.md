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
  lane, on the owner's word.

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

**Rules it fights.**

- `building-one-home-per-capability`: a second set of working rules, loaded beside the root
  `CLAUDE.md`.
- `outcomes-grant-covers-named-act` (a grant covers only the act it names): its Altitude step
  asks for "a version that also solves the next three requests" and for redesign of the process.
  That widens the act past the grant.
- `roles-one-role-per-agent`: its Range step has one agent do the work of a red team, a skeptic
  and other roles.
- Output style `shiv-stylisms` (short): it sets a demanding target for each task, which pushes
  length.

**Verdict: skip.**

- Gain if added: one page of AI failure modes and their countermeasures.
- Loss if added: about 2,000 words of context per task, and a push to widen scope past the
  owner's grant.
- Note: no row in its table names a failure mode that our rules lack. A check row by row is
  unknown past the seven rows above.

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
