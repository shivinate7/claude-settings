# Plan: three catalog plugins, add or skip

This plan assesses three plugins the owner named on 2026-11-01 21:32 CST: iceberg, Ambition
Lenses and Hypotize. It reads each plugin's own files, not only its README. Nothing was
installed and no setting changed. "Unknown" marks a fact no read confirmed.

## Verdicts

| Plugin | Verdict | Gold standard: one home per capability, no load on every task | Gap |
| --- | --- | --- | --- |
| iceberg | Skip (coordinator pick, 2026-11-01 22:55 CST, process-only) | Prose has one home: `lint/ste_lint.py` and the fresh-prose skill | A second prose rulebook that tells Claude to rewrite every plan and doc |
| Ambition Lenses | Trial, owner 2026-11-01 22:43 CST | Working rules have one home: the root `CLAUDE.md` | A second rulebook of about 2,000 words that a SessionStart hook loads into each task |
| Hypotize | Skip (coordinator pick, 2026-11-01 22:55 CST, process-only) | A plugin serves work that this repo's sessions do | Growth-experiment tracking on an outside service. No session here does that work |

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
  plain-prose lint). Home: `lint/ste_lint.py`.
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

The owner asked (2026-11-01 22:27 CST, per the lane's handoff, commit 97ac99a9): "we need to see
which is better, we can't just assume I'm right". The cases compare our rule and guard with the
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
  count owner corrections and unasked acts. The owner picked it: see the Trial section.

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

## Ruling

- **Ambition Lenses: trial.** Owner, chat, 2026-11-01 22:43 CST: "b, run the Ambition Lenses A/B
  trial" (see Trial). This replaces the coordinator's skip-all pick for Ambition Lenses.
- **iceberg and Hypotize: skip.** This is the coordinator's process-only pick (2026-11-01 22:55
  CST): skip all three, as `main` installs none. The owner's 22:43 answer changed only Ambition
  Lenses. Source: the roadmap step `plugin-assess-three`, its note.

## Trial

The owner picked the trial on 2026-11-01 22:43 CST. This section is the design only. No run has
started. The coordinator starts each run, because a lane does not call `create_session`. A fresh
Sonnet audit read the first draft for bias and found it tilted toward arm A and toward a null
result. This design applies its fixes.

**Question.** Does the Ambition Lenses text give a better lane outcome? Better means the owner
would merge the diff as is, the checks pass, and the work is right, not only small.

**A null result does not confirm skip.** It means the trial found no large effect.

### Cases

Three cases have a brief read word for word. Five more have a known base and PR, but their
briefs sit at the start of transcripts too long to page (60K to 180K characters per page of user
events). Their briefs are unknown. A case enters the trial only with its brief.

| Case | PR | Base | Brief | Known outcome | Chance of an extra act |
| --- | --- | --- | --- | --- | --- |
| tracking-turn-report-clash | #966, merged | 4b8037d | Read (event ec68be2c) | Brief asked one sentence in the output style. The PR also changed `lint/rule_audit.py`, `lint/rule_mechanisms.json` and the debt notes. The lane's report says `rule_audit.py` was "not named". 3 review rounds | Whether the extra files were needed for checks to pass |
| option-letters-match | #967, merged | 4b8037d | Read (event 536e545e) | Brief asked the check and its tests. The PR also changed `agents/designer.md` and a decision record. Skipped: naming the test-author's model (Stop hook, event 1428dea6) | Designer text and record fixes beside the check |
| windows-live-lock-flake | #941, merged | ce80331 | Read (event 7463dd84) | 2 files, in scope. The cause it named is not yet judged. Skipped: no model named for the reviewer (event bd773626); a notes line failed lint | The round-1 reviewer's two small test adds |
| guard-log-time-offset | #974, merged | 4b8037d | Unknown | Batch runner asked for a missed mod version bump and a dated comment (event 149159e0) | Version bump on a touched mod |
| install-log-offset | #1000, merged | 17492e5 | Unknown | PR body only: 8 files, 2 rounds | Unknown |
| playwright-cache-os-key | #970, merged | 4b8037d | Unknown | PR body only: 5 files, 4 review notes | Unknown |
| none-with-note-is-direction | #980, merged | ea92b0c | Unknown | PR body only: 7 files, 3 decision records | Unknown |

Event ids are transcript event uuids in each case's lane session.

Each brief is in `docs/plans/trial-briefs/<slug>.md`, word for word as the coordinator sent it.
A case's base commit is the `main` commit its lane started from.

### Arms

| | Arm A | Arm B |
| --- | --- | --- |
| Model and effort | Lane row of `agent-model-cap`: Opus, medium | Same |
| Prompt | Trial preamble, then the case brief, then the frozen step | Same |
| Base commit | The case's base | Same |
| Added system prompt | None | The plugin text below, as `append_system_prompt` |

**Arm B's text.** From `JamesFincher/ambition-lenses` at 6ecb9cc17be0a22e8de4b5c3e633bda5df791c7c,
word for word: `skills/ambition-lenses/SKILL.md` (SHA-256 starts `ab838038e029acab`), then its two
reference files, which `SKILL.md` names: `references/engineering-checklists.md` (`9fdd7386be35feee`)
and `references/examples.md` (`61d46c1a24446bd8`). So arm B never reaches for a file it lacks. The
coordinator fetches each from `raw.githubusercontent.com` at that commit at spawn time. A different
hash stops the run.

**What arm B differs in from a real install.**

- The SessionStart hook's 30 words ("invoke the ambition-lenses skill ... for the whole task") are
  left out. Arm B has the whole text from the first turn instead.
- With a real install the model chooses to call the skill. Arm B always has it, and the
  reference files load at once, not on demand.
- A real install puts the text in a tool result. Arm B puts it in the system prompt, which may
  weigh more.
- The lane's agents never see arm B's text. A builder writes most of the diff. So arm B tests the
  plugin's effect on the lane: how it briefs, what it asks for, what it accepts. The trial scores
  those briefs too (measure 6). An effect through the lane is diluted, so a small effect may not
  show.

**Trial preamble.** Both arms get this text first. Each line settles a conflict with the brief,
and the preamble wins.

> Trial run. These lines override the brief below where they differ.
> 1. Your agents branch from commit `<base>`, not from origin/main. Fetch no other branch and
>    read no commit after `<base>`.
> 2. Run the brief's review rounds as agents. Open no PR.
> 3. Push only to `archive/trial-<run>`. Message no session.
> 4. Skip each brief step that opens a PR, sends a message or writes the roadmap, and name it
>    as skipped.
> 5. The step file the brief names is below the brief. Do not fetch the roadmap branch.
> 6. End with your report. After it, print one line `=== guard.log ===`, then this session's
>    rows of `~/.claude/guard.log`, then one line with your count of tool calls.

`<run>` is a random two-letter code from the spawn list. A branch name does not show its arm.
Both arms of a case start at the same moment, so neither can fetch the other's branch before it
ends.

### Measures

The primary measure and the win rule are fixed here, before any run.

**Primary: accept as is.** A blind reviewer answers yes or no: would the owner merge this diff
with no change? It answers after it sees the checks' verdict (measure 2). An arm wins a case when
its diff gets yes and the other arm's gets no. Every other result is a tie. Arm B is better when
it wins 7 or more of 8 cases with a winner; arm A, the same. Any other split is no result.

| # | Measure | How it is read | Gold standard |
| --- | --- | --- | --- |
| 1 | Accept as is (primary) | Blind reviewer | Yes |
| 2 | Checks pass | The coordinator runs `ste-changed <base>` and the tests the diff touches, on each branch | All pass |
| 3 | Work is right | Blind reviewer: does the diff do what the brief asks? For a bug, is the cause named right, with evidence? | Yes |
| 4 | Extra acts | Blind reviewer: each file or hunk the brief did not name, sorted as needed (a check fails without it), useful (the owner would keep it) or noise | No noise. Needed and useful acts count for the arm |
| 5 | Skipped acts | Blind reviewer: each act the brief needs that the diff or the report lacks, such as naming each agent's model | 0 |
| 6 | Agent briefs | Blind reviewer: the briefs the lane wrote to its agents, with arm words removed. Does each carry the task, the check and the report cap (rule `roles-brief-contents`)? | Each does |
| 7 | Refusals per tool call | Rows after the `=== guard.log ===` line, over the printed tool-call count | Lower |
| 8 | Report words | `wc -w` of the text before `=== guard.log ===` | The brief's cap or fewer |
| 9 | Tokens | `get_session` `context_usage.used_tokens` at the end, minus arm B's text (about 2,700 for `SKILL.md` alone; the coordinator counts the full text). Agents' tokens are not in it, in either arm | Lower, at equal outcome |

**Blind reviewer.** One Sonnet reviewer per diff, in a fresh context, so no diff is judged against
another. Each case has three diffs: arm A, arm B, and the merged PR as a calibration diff. Each
reviewer gets the brief, the frozen step, `git diff <base>..<branch>` with no commit messages, and
the checks' verdict. Before it scores, the coordinator removes arm B's words from added prose
("Altitude", "Depth", "Range", "Speed", "lens"). After it scores, the reviewer guesses the arm,
and the coordinator logs how often it guesses right. A hit rate well above one in two means the
blinding leaked.

**Noise.** One case also runs arm A twice (an A-versus-A pair). If the two A runs differ on the
primary measure, one run per arm cannot separate the arms, and the report says so.

**Confounds.**

- The global rules load from today's `main`, not from the case's date. That is the same in both
  arms. Some faults in the case history are now rules or guards, so both arms may avoid them.
- `main` holds each lane's merged fix. Preamble line 1 forbids reading past `<base>`, but nothing
  enforces it. Arm B's "go to the rawest source" may push it to look. The coordinator checks each
  run's transcript for a fetch or read past `<base>`, and drops that run's case.
- The three ready cases come from one coordinator, and two share a base. All three are normal-size
  fixes. The plugin's own table says "Trivial: answer directly", so very small cases would favour
  a null result. None of the three is trivial.

### Spawn list

Three cases are ready now. Each run is a new session, Opus at medium effort. Its prompt is the
preamble, the brief file, then the frozen step, with `<base>` and `<run>` filled in.

| Run | Brief file | Base commit | Frozen step (roadmap commit) | Arm |
| --- | --- | --- | --- | --- |
| sx | `docs/plans/trial-briefs/tracking-turn-report-clash.md` | 4b8037d4145b27046ff7526238eead4aaa60529f | f122aabe41ed0183907ce7652939a59a12039458 | A |
| lg | `docs/plans/trial-briefs/tracking-turn-report-clash.md` | 4b8037d4145b27046ff7526238eead4aaa60529f | f122aabe41ed0183907ce7652939a59a12039458 | B |
| qm | `docs/plans/trial-briefs/option-letters-match.md` | 4b8037d4145b27046ff7526238eead4aaa60529f | 891446e4d2b60053a4f8962a3097a309e11ceba9 | A |
| mf | `docs/plans/trial-briefs/option-letters-match.md` | 4b8037d4145b27046ff7526238eead4aaa60529f | 891446e4d2b60053a4f8962a3097a309e11ceba9 | B |
| ct | `docs/plans/trial-briefs/windows-live-lock-flake.md` | ce80331615bda3181ff09628065666b4b766c12c | none | A |
| ux | `docs/plans/trial-briefs/windows-live-lock-flake.md` | ce80331615bda3181ff09628065666b4b766c12c | none | B |
| ka | `docs/plans/trial-briefs/option-letters-match.md` | 4b8037d4145b27046ff7526238eead4aaa60529f | 891446e4d2b60053a4f8962a3097a309e11ceba9 | A (the A-versus-A pair) |

The frozen step is `roadmap/data/steps/<slug>.json` at that roadmap commit, the last before the
brief was sent. The run codes came from a random draw. The arm column is for the coordinator only.

Three cases cannot reach a result: the win rule needs 7 wins in 8. Two ways to reach 8:

- **(a) Past briefs.** The coordinator gives the five unknown briefs from its notes, if it kept
  them. Paging the transcripts costs about 4 to 15 pages per session.
- **(b) Next lanes, both arms as shadows.** For each of the next five lanes with a normal-size
  fix, two shadow sessions get the same brief and base, one per arm, under the same preamble. The
  real lane runs as usual. Its merged diff is the calibration diff, not arm A. So both arms meet
  the same preamble and the same limits, and briefs cost nothing to find.

Recommended: (b). The arms stay equal, and the calibration diff shows what the real process
gave.

### Shadow pairs for the next five lanes

The coordinator picked option (b) on 2026-11-01 23:08 CST.

- **Which lanes qualify.** A lane on claude-settings whose brief asks for a normal-size change:
  one fix, check or rule, with a check that proves it done. Not a trivial edit (one word, one
  pin), not a survey or plan, and not a screen. The first five such lanes after 2026-11-01 23:08
  CST qualify, in the order the coordinator sends their briefs.
- **When.** The coordinator spawns the pair in the same turn it sends the real lane its brief. Both
  shadows start together.
- **Base.** The `main` commit the real lane starts from, read when the coordinator sends the
  brief.
- **Prompt.** The trial preamble, then the real lane's brief word for word, then the step file
  at the roadmap commit of that moment. Arm B adds the same text as the ready runs, hash-checked.
- **Run codes.** A new random two-letter code per shadow. The coordinator keeps the arm key.
- **Brief file.** The coordinator saves each brief to `docs/plans/trial-briefs/<slug>.md` on its
  next record PR.
- **Calibration.** The real lane's merged diff is the third diff for that case. A dropped or held
  real lane gives no calibration diff; the case still counts on its two arms.

### Transcripts on the owner's computer (optional)

The repo cases suffice for the trial. A session on the owner's computer adds the true outcome:
what he typed back to a session.

- `~/.claude/projects/*/*.jsonl` for the case sessions he ran on his computer: his messages after
  each lane's report, to count corrections.
- `~/.claude/guard.log` on that computer: refusals in the same sessions.
- `~/.claude/handoffs/*.md`: rulings that name a correction.

Why: the repo holds only corrections that became a record. A correction he typed and nobody
recorded is missing here.
