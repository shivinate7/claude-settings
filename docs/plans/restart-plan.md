# Restart plan: how claude-settings lands work after the freeze

Owner's plan, kept by the retrospective session (session_013NEJKz5AWFJhGvmCUoi6wQ, child of the
coordinator session_013NEJL2hB1pLZPDpzas7VgB). Rewritten in place each time a point settles; git keeps
the history. Last rewrite: 20:03 CST Nov 11. The owner's list closed at 18:43 CST Nov 10; R21 to R45 came after.

Judged by two priorities, in order: accurate, then as fast as possible without losing accuracy.

Read it top to bottom: five stages in the order they run. Each stage holds the rulings that govern it,
in the owner's words with the time. Ids (R1, G1, D1) are stable names, not an order.

## Why this order

The words come first, because every later brief uses them (3.0, G1-G15). Next comes the split of the
guard test file (R26 part 4), while few lanes are open. The rest of stage 3 then runs in parallel, and
stage 4 runs beside it (R25). Only four items wait on another: 3.2 runs with 3.1, 3.12 after 3.11,
3.14 in R28's order, and R33 in 3.7 after R32's audit. Stage 3 covers what loses whole CI runs (3.1, 3.2, 3.4, 3.5) and the loop
that sends lanes back (3.3, 3.7, 3.8). It also covers trust in guards (3.6, 3.9-3.12), the express pass
for prose (3.13), prose that tends itself (3.14), and token spend (3.15). Stage 4 makes the owner's side mechanical: one home and one wake
per answer, easy relays, debts and notes kept in place, session ids that survive a restart. Each is
fixed once, before lanes resume, so the resumed lanes run under it. An item still open (D1, D3) holds
no stage.

## What happens next

1. The drain finishes (stage 1); the H1 lane lands as the one exception.
   Then a fresh start. Owner 10:52 CST Nov 11: "once the drain completes i'll archive coordinator,
   batch runner, and all other claude-settings sessions except you. and respawn the others as new".
   Before he archives: the plan follow-up PR is merged, #2591 (Windows guard shard caps) lands (owner
   12:55 CST Nov 11, to the coordinator: "yes land #2591 before archive"), and each session writes its
   handoff with what it holds open. #2593 (cloud CI-done wake) and lane mail-send-no-file carry over in
   the handoffs if they have not landed. R22's guard is not built yet, so after the respawn the retrospective session
   finds the new sessions by their tags and rewrites every stored session id by hand.
2. Stage 2 is done (#2575, #2579). Later rulings land in the next plan follow-up PR, which the
   coordinator opens. The retrospective session opens no PRs.
3. Stage 3 starts with 3.0, then the test file split; then every other item may start, with stage 4
   beside it. Batches follow R26 (3.4). Triage has every ruling filed as a step.

## Stage 1. Drain

In progress (owner chat Nov 10, between 13:31 and 14:07 CST: "im drianing as we speak"). The freeze
holds (owner 09:18 CST Nov 10): no new lanes except fixes of items landing on main. Left at 10:50 CST
Nov 11 (GitHub read): #2379 and #2431 in batch 79 (#2587, draft, CI not started), then #1099, and
#1166, #2563, #2378 stacked on #2431. Last merge: batch 78, 08:26 CST.

- **R23. The drain ends at the named queue.** Owner 19:23 CST Nov 10 picked "Named queue". Outcome:
  with 682 open and 95 merged since 00:00 CST (GitHub search, coordinator, 2026-11-10 19:23 CST), draining all of them would hold the plan for about a week.
  1. The drain ends when the named queue lands: batch 74b (#2574), batch 75, and the coordinator's
     next-to-release list at 19:23 CST (#2563, #2566, the ten former #2563 waiters, #2575, #2542).
     #1805 left the queue for item 3.6 (owner 09:12 CST Nov 11).
  2. Triage sorts the other open PRs (662 at 23:51 CST, coordinator) against this plan. It closes a PR whose purpose a ruling here
     replaces, with its branch kept so it can reopen. The rest wait as stage 3 input.
  3. Stage 2 starts as soon as #2575 is on main, without waiting for the sort.

Freeze exception, owner 16:02 CST: "i see yes fix it then". One lane makes the settings.json guard
matcher route the GitHub MCP write tools to guard.py (hole H1, under R11 below), with a test that every
tool the guard judges is reached by the matcher.

## Stage 2. Land this plan on main

One prose PR holds every settled ruling below in the owner's words with its time (#2575). It takes the
normal docs-only route; later rulings land in one follow-up PR (coordinator message to the retrospective session, 19:15 CST:
"Your later commits on restart-plan (74ce03ec1 and after) land in one follow-up PR after #2575 is on
main").

## Stage 3. Change how every lane flows

Before any other lane starts. An item may hold several rulings; triage splits it into one lane per
step.

### 3.0 One glossary of roles, the same on local and cloud

Step glossary-same-local-cloud. First because every later brief uses its terms.
Owner 13:54 CST Nov 11: "a": 3.0's records half (GLOSSARY.md, decision session-tiers, the CLAUDE.md
lines; G1-G3, G6, G7, G9, G10, G12, G13, G15) starts now as one lane, before the fresh start, so the
respawned sessions run on it. Its code half (G11's local and cloud splits, which touch the guards) waits
for the guard test file split.

- **G1. Who acts.** Owner 14:23 CST Nov 10: "the who is good, but i can make a grant or ruling, so can
  arbiter (marked as such, and a tier below)". Three kinds of actor: the owner, a session, an agent.
  The owner and an arbiter make grants and rulings. An arbiter's is marked as the arbiter's, ranks
  below the owner's, and the owner can overturn it. Today an arbiter makes rulings only
  (decision session-tiers, Arbiter); this adds grants. An arbiter's grants never include Opus (G13).
  Home: decision session-tiers, GLOSSARY.md.
- **G2. Session roles, the same on local and cloud: coordinator, triage, batch runner, lane, arbiter.**
  Owner 14:23 CST Nov 10: "coordinator approved", "batch runner yes agreed", "lane yes agreed but solo
  should be able to merge ideally like it can be a one stop shop sometimes", "this collapse feels good".
  Solo, one lane and lane session collapse into one role, lane. A lane the owner starts, with no
  coordinator above it, may merge its own PR under a merge grant. The terms shape, tier-as-separate-axis
  and orchestrator drop. Home: decision session-tiers, decision lanes-start-as-agents, GLOSSARY.md.
- **G10. Roles are hats.** Owner 14:33 CST Nov 10: "yes hats model works". A role is a set of jobs. In a
  solo run one lane holds every role it needs: it writes its own page items as triage and merges its own
  PR as batch runner. How many sessions share the roles depends on the size of the run, never on local
  or cloud. A solo run the owner is watching asks in chat, and writes a page item only when it must
  wait on him while he is away.
- **G12. A lane's behaviour follows the size of the work.** Owner 14:55 CST Nov 10: "yes A this is good".
  Any lane builds a short list of edits itself when nothing can run in parallel; otherwise it fans out to
  agents, whoever started it. Merges rules roles-solo-builds-short-edit-list and
  roles-orchestrator-never-builds. Home: CLAUDE.md, decision session-tiers.
- **G13. The arbiter is a decider only.** Owner 15:08 CST Nov 10: "isn't arbiter just a decider, why
  would it ever have [agents]"; "yes" to the form. It makes rulings in its repo, one tier below the
  owner. It may start only read-only agents (Explore, refuter) to gather evidence. It builds nothing,
  starts no lanes, and grants no Opus. The arbiter session itself runs Opus (agent-model-cap:61).
  Rewrite session-tiers:81 ("a standing session and an orchestrator"). Home: decision session-tiers,
  GLOSSARY.md.
- **G3. Archiving.** Owner 14:29 CST Nov 10: "archiving as part of the batch runners responsibilities is
  approved, with the coordinator archiving the ones that it decides to spot (in general though i assume
  that with my rules on how PRs should close older prs sooner that would mean batch role has more
  exposure to superceded prs/sessions and will be able to archive them)". The batch runner archives each
  lane after its merge, and each lane whose PR was superseded. The coordinator archives a lane it
  decides to stop. Builds on owner 2026-11-06 11:38 CST (decision session-tiers).
- **G7. Standing sessions compact, they are not replaced.** Owner 14:29 CST Nov 10: "both it and triage
  and stuff in general are no longer replaced they just compact graciously it's odd that the other
  prose still remained". Matches session-tiers:18 (owner 2026-11-01, item 109 b). Stale text to
  rewrite: session-tiers:81 (arbiter "rotated before it goes stale, like triage"), GLOSSARY.md:63
  ("Triage, batch runner and arbiter rotate"), skills/project-ops/SKILL.md:3 and :17. Rewrite approved,
  owner 14:32 CST ("agreed on the rewriting from g7").
- **G6. One role proof, local and cloud.** Owner 14:29 CST Nov 10: "yes cloud tags can be optional
  agreed", "local sessions do have sesion id yes". A session proves its role from one roster both
  places read (the Standing sessions list on the roadmap branch); cloud tags become optional. Local
  sessions have a session id, so the split is chosen, not forced.
- **G11. One behaviour on local and cloud.** Owner 14:36 CST Nov 10: "agree on your proposed close on
  topic 1"; 14:37 CST: "yes it can be closed". Every split a rule chose is removed, so both places
  behave the same. A split the platform forces lives only inside the tool, never in a role's
  definition. Splits to remove in this lane: two tests for "cloud" in the code; guards that judge only
  one of start_session and create_session; the merge role file on the cloud only. Also the load brake on
  the owner's computer only, and a lane the owner starts that cannot merge on the cloud yet
  (docs/todo.md, "Let a solo session merge", owner 2026-11-02 14:02 CST). Deferred to a later build phase (owner 14:37 CST,
  "can be targeted after/later"): the details of forced splits, mainly a team that mixes local and
  cloud sessions while the mailbox bridge (MAILBOX_REPO) is off.
- **G9. Triage always writes the waiting page.** Owner 14:32 CST Nov 10: "yea triage always writes the
  waiting page". Replaces the three definitions ("where triage runs", "a project with a triage thread",
  "when no triage lives").
- **G15. The owner talks in two places.** Owner 16:46 CST Nov 10: "Yes that's approved". In a larger
  build: the page, for anything waiting on him (his answer wakes the session that asked); the
  coordinator's chat, for anything new (it starts the other sessions, so it routes the item). Never a
  lane directly. Side sessions such as this retrospective hold rules talk only. Home: decision
  session-tiers; skill waiting-page.
- **G14. The triage artifact is one page.** Owner 15:52 CST Nov 10: "when i say triage artifact i meant
  both given that they've merged into one (and if you thought otherwise that's a prose fault that needs
  correcting)". skills/roadmap/SKILL.md:6 says so; GLOSSARY.md has no row for it, and the roadmap skill's
  trigger words still say "roadmap page". One glossary row: page, the repo's one page that triage
  writes, holding the waiting items and the Status tab. "Roadmap page" retires. Home: GLOSSARY.md,
  decision questions-go-to-owner.
- **G4. Plain names.** Owner 14:29 CST Nov 10: "check fix reviewer should be the name", "review log is
  fine", "feedback log is good too". 14:33 CST: "i meant let's call it the "check fix reviewer" (or find
  a better name that's cool too)"; 15:44 CST: "sure that's fine" to fix verifier. Fix check -> fix
  verifier (the reviewer that verifies one fix). Reason: "check" already names a lint, test or CI job in
  the glossary, so a name with "check" in it would clash. review record -> review log; the per-session
  inbox file -> feedback log. The mailbox keeps its name.
- **G5. Rounds are numbered by the review they answer.** Owner 14:29 CST Nov 10: "approved on fixing the
  naming trap on the rounds". The fix after review 1 is labelled "Fix for review 1", not "Round 2 of 3".
- **G8. A wrong term gets a gentle correction.** Owner 14:30 CST Nov 10: "i often call things by the
  wrong terms sometimes and don't want that to result in confusion for claude and instead be met with
  strong pushback and a gentle correction"; form approved 14:32 CST ("agreed on g8"). Three cases: the
  word maps to one term: act, and add one line "You said X; the term is Y, which does Z". The word names
  the wrong session or role: one line saying whose job it is and why, then route it. The word fits two
  terms: ask before acting. Home: CLAUDE.md speak-one-name-per-thing and the output style's
  style-wrong-tier-one-line, rewritten in place.
- **R30. A consultant role, started by the owner.** Owner 10:54 CST Nov 11: "im able to spawn a
  retrospective or a consultant, basically someone like you who's literally a course correction vehicle
  for me to chat with from a more outsider lens -- or realistically should i be working wiht a
  coordinator for this". Box answer before 10:58 CST: "Add consultant role". A sixth session role, the
  consultant. The owner starts it on demand in claude-settings; no coordinator starts it. It talks with
  the owner, runs read-only audits, keeps one plan file rewritten in place, and sends each ruling to
  triage. A finding about another repo goes to that repo's triage. It builds, merges and decides
  nothing; an arbiter decides, a consultant helps the owner decide. It ends when its plan lands. The
  name "advisor" is not used, since the built-in advisor (`advisorModel`) has it. Home: decision
  session-tiers and GLOSSARY.md.

### 3.1 Checks that can refuse a merge run in CI

- **R2.** Owner 14:07 CST Nov 10: "i agree speed maximization is a good idea". The merge tool runs no
  check of its own that can refuse a green batch. It reads CI's verdict, the PR-body lines (R15), and
  whether the batch is current with main. The Retire check moves into CI. Cause: batch
  #2551 green in CI at 11:15 CST, refused at merge 11:50 CST by the Retire check's 600 s local limit;
  one full CI run lost. Home: decision debt-close-runs-retire; step retire-check-whole-suite;
  merge.readyChecks in decision lanes-run-no-full-ci-job.
- **R15. One PR template.** Owner 16:22 CST Nov 10: "no pr template: yes that seems like a must have".
  .github/pull_request_template.md holds the PR-body lines the merge tool reads (`Retire-run:`,
  `Drops-lines:`), so every PR has one shape and no session reports "no PR template". Other repos get it
  through skill project-ops. Unmeasured: how many PRs are refused today for a missing line. Step
  pr-template-merge-lines. Home: decision debt-close-runs-retire.
- **R17. A repo with no CI gets a starter CI, not an exemption.** Owner 16:25 CST Nov 10: "repos that
  have no CI need to get an easy exemption so that they can still call claude-settings but basically
  things that need CI don't pertain to them -- how can that become a thing?"; 16:36 CST: "this is
  approved and sounds better than allowing no ci". Keeps decision same-check-kinds (owner item 87,
  2026-10-30: every repo runs the same kinds of checks, as many as its size needs). Skill project-ops
  writes a starter CI to any repo without one: quick checks on what the repo holds (links resolve,
  scripts parse, JSON parses) inside the shared all-jobs-passed rollup. When the merge tool or lane lint
  refuses for no CI, the refusal names that one step as the fix. Folds in roadmap step c33 (repo home,
  the one repo with no CI on Oct 22). Cost: one workflow file per such repo and a short CI run per PR.
  Home: decision same-check-kinds; skill project-ops.

### 3.2 Time limits end hangs only

With 3.1, this stops a green batch from being refused at merge.

The stopgap does not wait for the drain. Owner 12:11 CST Nov 10, decision ci-job-caps: "generously raise
time limits in the interim so that tests dont fail off time". Case: it was not done. Main had no
finished push run from 11:56 CST Nov 9 to at least 11:50 CST Nov 11; 11 runs were cut at the Windows
guard shard cap (debt windows-shards-outgrow-caps). The coordinator queued the raise as a fix lane at
11:56 CST Nov 11. Owner 11:53 CST Nov 11: "i'd already told triage/coordinator to just raise the test
limits and i had shared so mayn gripes arleady about artificially timed tests ... pretty frusdtrating".
Under R16, the missing guard: a main job that ends at its cap raises an alarm at once.

- **R3.** Owner 14:09 CST Nov 10: "time limits as a rule make little to no sense when they feel
  arbitrary and are not outcomes related ... I understand keeping time limits at some point for letting
  hung tests end". Form accepted 14:10 CST ("yes, that three-part form matches what I meant"):
  1. Stop on silence, not total time: a run ends only after it prints nothing for a while.
  2. A stop reads "hung", never "failed": never red, never a merge refusal; retried once, then reported.
  3. A total-time limit that must stay (CI billing) comes from measured green runs each time, never a
     number stored in code.
  Details, owner 14:24 CST Nov 10 (answers to triage's four points):
  - A check that gives a verdict (lint, tests, Retire) stops on silence, reads "hung", retries once. Any
    other background command is only reported and keeps running (decision stall-watch). ("yes that's ok")
  - Every CI job keeps a total-time limit, computed from recent green runs by a script, generously
    large. Local tools use the silence stop only. ("it should be generously large maybe")
  - merge.deadlineMinutes is computed each time from the current CI limits; reaching it reads "CI still
    running", never a refusal. ("this needs to be a moving target")
  - The silence window is measured per tool from the longest gap between output lines in green runs.
  - Margins multiply, never add: "+5m is not as generous as like +1.5x".
  - A new CI job with no green runs: its nearest similar job's computed limit x1.5. If it hits that
    limit, it is flagged as misjudged and moves to the largest current job's computed limit x1.5. Owner
    14:36 CST: "b is probably fine for now, with some sorta flag that if it quickly fails that it was
    misjudged and it goes to largest current job x1.5"; 14:37 CST: "if it was just made and it then
    fails in its first run or two that's a sign it was misjudged". Replaces the stored 60 min in
    ci-job-caps.
  - A job stops being new after its first green run. The nearest similar job does the same kind of work
    (lint, test, mutation, build); with none, the largest current job x1.5. Owner 15:03 CST: "yes thats
    fine agreed".
  Replaces: merge/merge.py LINT_SECONDS 1200, lint/check_debt_retire.py TIMEOUT 600,
  hooks/mutate_guard.py and janitor/mutate_sweep.py 1200, lint/check_python_floor.py 300.
  Home: new decision time-limits-end-hangs-only; decision ci-job-caps rewritten to match.

### 3.3 A review log survives a clean main merge

- **R1.** Owner 14:07 CST Nov 10: "i agree on letting it survive a clean merge where batch ci sees the
  problem rather than asecond review". And: "i agree it shd be mechanical tooo". A log stays valid when the new
  head differs from the reviewed head only by a clean merge of main, with the lane's own diff unchanged.
  The merge tool proves it (for example with git range-diff). Any difference keeps today's rule. Batch CI
  catches clashes with main. Home: decision pr-review-record, rewritten in place. Folds in steps
  fix-check-after-main-merge and fix-check-chain.

### 3.4 A batch closes on a limit

Step batch-freeze-lane-set-enforce, already doing. Owner, same answer: "the limit isn't the problem,
it's how the limit batches that's the problem". How many lanes start is left to this step for now.

- **R26. Batches stop wasting CI.** Owner 09:20 CST Nov 11: "i need a review and then a strategy that
  makes me parallelize as much as possible, without losing time when things start merging into main".
  And 09:21 CST: "batch merges themselves were made to avoid CI waits and to have things go faster". In
  the question box, answered by 10:00 CST, he picked these parts.
  1. A lane's own checks run what made batches red: the Windows slice, mutation tests on the files it
     touches, and signed-commit cases (folds into 3.5).
  2. A lane dropped from two batches leaves the queue for a fix lane.
  3. No self-made reruns: the merge tool stops the records-page push after a green run, and a red main
     is fixed before the next merge, not waited out.
  4. Busy files in turn (box answer 10:05 CST, "Both"). The batch runner puts lanes that touch the
     same busy file (the main guard file, its tests, its mutation tests) into back-to-back stacked
     batches, never one batch. The guard test file is split into one file per rule. The split runs
     first in stage 3, while few lanes are open.
  Stays as ruled: decision batch-freeze-lane-set (owner 2026-11-08 20:24 and 20:31 CST): the set freezes
  at build, the next batch stacks on the running one, a red run drops only the blamed lane. Its tool
  check is this item's step. One batch runner: merging is one at a time under one lock (merge.py).
  Evidence (audit 09:37 CST, last 15 batch merges, 256 lanes): 3030 CI minutes, 677 on merged heads.
  74 builds became 15 merges, with 147 lane drops; two lanes were dropped in 5+ batches each. Lane
  wait, last commit to merge, has a median of 536 min, 397 of it before the build. A lone CI run takes 33-38 min (5 runs). Merge
  queue: GitHub offers it to organization repos only.

### 3.5 Lane lint runs once per lane; batch CI fails fast

- **R4.** Owner 14:54 CST Nov 10: "is there no truly fast way that retains accuracy?"; 14:56 CST: "yes D
  is approved". Keep the lane lint run at hand-off (inside each lane, in parallel). Drop the runs at
  join and on the batch head. Batch CI runs lint first and cancels the rest of the run at once when
  lint goes red; the red files name the lane to drop. A builder first confirms that CI cancels on first
  failure and that each red lint maps to one lane. Home: decision lanes-run-no-full-ci-job, rewritten in
  place.

### 3.6 One guard cull now, then notes only

- **R5.** Owner 15:04 CST Nov 10: "i'd say option e works for now with a revisit maybe to threshold
  lanes if it turns out to be problematic". One cull lane fixes or deletes each guard or check with a
  recorded wrong refusal (60 "false alarm" lines in docs/debts/notes.md). It fixes each one, and
  deletes it only when its wrong refusals cost more than the harm it stops (rule
  building-guard-needs-incident stays; owner 15:23 CST: "b ... this is fine"). The list also covers the
  lane pick guard's wrong fires and the Departs-from separator and Recovered-line fires (owner 15:18
  CST: "A is fine -- but the coordinator probably has way more data on how hooks have been acting than
  your small sample size does"); the coordinator sends triage its record of hook fires for the same
  list. After it, wrong refusals are notes only. If they turn out to be a problem again, revisit a
  threshold (a guard with 3 recorded wrong refusals gets its own lane). Home: new decision
  cull-guard-wrong-refusals, beside cull-rules (PR #2568, branch cull-false-alarms-once).
  The cull also judges the message guard between sessions, #1805, with its fix #1849, as one pair.
  Owner 09:12 CST Nov 11, in the coordinator's chat: "q2 B" (take #1805 out of the drain; both go to
  stage 3). Alone, #1805 wrongly refuses 136 of 204 ordinary coordinator messages; with #1849, 13 of 204
  (#1849's round 3).
- **R24. Every refusal names a way out that works.** Owner 09:16 CST Nov 11, in the coordinator's chat:
  "yes file it for stage 3". Every guard refusal and ask names an allowed way out, and a test proves each
  named way out passes the guard. Step refusal-names-way-out. Runs beside the cull.
- **R16. A mistake is filed as a missing guard, by a hook.** Owner 16:22 CST Nov 10: "i thought i've
  already set something really high up in claude.md or elsewhere that sessions/agents should never
  assume an error is their own and instead should strongly be raised awareness that any error they make
  might be a strong INDICATOR that a guard/something-0mechanical should be in place?"; 16:25 CST: "yes
  agreed-- that or we create a hook taht looks for this kind of prose when the session says it so taht
  way the HOOK/judge files it not the session itself". Rule building-mistake-names-its-guard opens:
  "Read a mistake first as a missing guard or check, never as a fault to own: the way we work should
  make accidents hard." The report gives `Cause:` (what made it easy) and `Guard:` (built, queued or
  debt). A Stop hook spots a mistake told in a reply and its judge files the missing guard to triage,
  so the session does not file it itself. It runs inside the existing Stop hook; no new process.
  Cause that led here: the feedback-log hook writes a message heading without telling the session, so
  it wrote a second one twice (step inbox-dup-heading-merge). Home: CLAUDE.md
  building-mistake-names-its-guard; decision guard-remedy-not-to-owner.
- **R20. A pass claim needs a verdict line.** Owner 17:17 CST Nov 10, quoting a session: "I told you
  several earlier lane lint runs "passed". They did not. Every run exited 1, and I misread my own echo
  exit code as the lint's"; 18:36 CST: "yes". Rule tokens-run-through-verdict is enforced by nothing on
  main (only quoted in a guard_stream.py remedy). (1) A "passed", "green" or "clean" claim in a report or
  a message to a parent cites a verdict line from this session's verdict log. The report guard refuses
  an uncited claim, remedy "run it through verdict". (2) Lint, ci-job, tests and the merge tool's
  release check run only through `verdict`; a bare run is refused with that form. Both run inside
  existing guards; no new process. Home: CLAUDE.md tokens-run-through-verdict; decision
  guard-remedy-not-to-owner.

### 3.7 One model table

- **R8.** Owner 15:44 CST Nov 10: "on #1 -- A seems best". The role table in decision agent-model-cap is
  the only home for each role's and round's model and effort. The spawn guard requires or fills in the
  row's model and effort (today it only permits them, guard.py:3783-3788, so a spawn with no model runs
  reviewer.md's Haiku). The merge tool checks the model that ran, not the log's text. Agent files, brief
  markers and checks read the table. Each model ruling lands in one lane that changes the table and
  every reader together. Cause: rulings 279 d, 439 and 444 a reached main 12-57 h late and in pieces;
  359 a, 359 b, 289 and 295 a are not on main. Home: decision agent-model-cap.
- **R33. Every role has a chosen model and effort, with a reason.** Owner 11:09 CST Nov 11: "i do
  think these roles that have defaults need to have decided models and why -- similarly maybe an
  evaluation of what else can be a first try haiku vs what needs to go higher and at what effort
  levels". Rows in the model table that no ruling chose today: main session, coordinator, triage,
  batch runner (through "separate sessions"), general-purpose agents, and every skill. Each gets a
  model, an effort and a one-line reason. An evaluation then tests each role on the cheapest model
  that passes its checks. It reads measured outcomes per role and model: review pass rates, fix
  rounds, builder third tries, and cost from R32's audit. Known data: Haiku round 1 fails 79% of
  reviews, Sonnet 38% (R9; the share that is noise is unknown). A row moves only on a measured pass
  rate. A move above Sonnet needs the owner's grant (rule roles-sonnet-is-the-ceiling). Runs after
  R32's audit, and folds in docs/todo.md line 9 (roadmap step c201: one lane per role on the
  next model down) and debt lane-model-recheck (whether any lane should run Opus). Home: decision
  agent-model-cap. Owner 13:52 CST Nov 11: "i'd say all three stay on opus for now until 3.7": the
  coordinator, triage and the batch runner respawn on Opus at the fresh start.

### 3.8 One rounds record; no round 3 after a pass

- **R9.** Owner 15:44 CST Nov 10: "yeah i never wanted round 3 if it passed earlier and was so confused
  to see that it was occuring"; "agreed A -- can look into the sonnet noise thing later". Fold the 15+
  rounds rulings into one record. Round 1 runs on item 359 a's model (Sonnet for a guard or check
  change, the role's model otherwise). Fixes are verified per G5. Correction, owner 16:07 CST Nov 10
  (relayed; step rounds-rules-one-record): round 3 follows owner pick 471 a
  (2026-11-09 23:39 CST, step review-state-guard-needs-round-3) as it stands. A guard or check change
  that passes round 1 is done, and a fix verifier PASS ends review too (owner, 2026-11-13 18:35 CST). The net-value test is
  only for an unclear case that cannot finish by the end of the rounds (the 2026-10-15 "still
  unfinished" valve in hold-unsafe-after-round-3). Evidence: round 3 found a failure 0 of 14+ times
  after a clean round 2; the net-value hold caught 6 real holes. Deferred: Sonnet round 1 for every
  logic change (Haiku round 1 fails 79% vs 38%; noise share unknown). Home: decision
  hold-unsafe-after-round-3; CLAUDE.md roles-review-cap-three and roles-third-round-steps-up rewritten.
- **R31. A builder resolves a test merge conflict; a check proves no test was lost.** Owner 11:02 CST
  Nov 11, box answer: "as long as it's well defined and doesn't create loop holes builder plus check
  definitely seems ideal no?"; and in chat: "yea that check should just protect it as the hand off
  happens usper often and it's for sure a point of contetnion". It changes page items 420 a (Nov 8
  10:05 CST) and 437 a (Nov 8 12:16 CST) in decision builders-cannot-edit-tests. Today a test conflict
  in a merge stops the builder; a fresh test-author takes the whole merge, and a review round follows.
  The outcome those rulings protect stays: no side's tests are silently dropped. A check now protects
  it, and the builder resolves the merge. The check reads test files with the language's own parser.
  At the merge commit it refuses each of these:
  1. A test case from either parent is missing, renamed or moved to another file.
  2. A test case's body differs from both parents' versions.
  3. A skip or expected-fail mark, or a changed assertion, that neither parent had.
  4. New test content that neither parent had. That stays a test-author's work.
  5. A change to test config beyond one parent's version, or any change to a mutation test. Page
     item 447 a (owner 2026-11-08 17:19 CST) stands: a merge that conflicts in a mutation test
     still goes to a test-author.
  Each case is shown red on a dropped or weakened test before the route opens. Until then the old route
  stays. It changes a guard, so the rounds and the net-value rule apply. Home: decision
  builders-cannot-edit-tests, rewritten in place.
  Beside it, the same root (triage 11:26 CST Nov 11, from an incident the owner shared in another
  repo): a test-author briefed to write red checks needed new tooling, was refused, and had to ask
  the owner. Step brief-role-scope-check catches a brief whose paths do not fit its role at spawn,
  and sends tooling to a builder first, whose red run is its proof.
  Owner feedback 12:57 CST Nov 11 (a tile-windows coordinator, relayed by the coordinator 13:00 CST)
  widens that step: four more incidents, and a refusal for a resume whose worktree is gone.

### 3.9 A hook refusal gets a short correction

- **R10.** Owner 15:44 CST Nov 10: "i never want my hook to have one spew out the whole thing again
  after -- as i fixed long ago in how the done deviations inputneeded hook works, that should be viewed
  as a best practice for other hooks that make you regurgitate output again".
  guard-remedy-not-to-owner:177 already says "post only the corrected lines ... Never send the report
  again", but no refusal text says it. Each Stop-hook refusal ends with that line. Home: decision
  guard-remedy-not-to-owner. Recurred 12:41 CST Nov 11: the report-shape refusal led this session to
  post its whole report again. Owner 12:42 CST: "i really dislike when the hook makes my sesison
  repeat everyhting and add an edit in to the output, i really want that each of these hooks/guards
  only adds the necessary additional text".
- **R14. A fix to a session's own notes prints nothing.** Owner 16:22 CST Nov 10: "fixed my notes
  question: yes". A Stop-hook refusal about a session's own notes (feedback log, handoff) is fixed with
  no line to the owner, since the reply did not change; guard.log still records it. A builder first
  confirms a Stop can end with no text. Step notes-fix-no-owner-line. Home: decision
  guard-remedy-not-to-owner.

### 3.10 One catalog of every hook and setting

- **R11.** Owner 16:00 CST Nov 10: "A -- but also i kinda meant how when questions reach triage, do the
  pre tool question use stuff run on it just like it would when uqestions used to come in line in the
  chats?". docs/catalog.md (lint/hook_catalog.py) lists all 36 hooks but no permissions, autoMode rules,
  env, cloud-only allow rules, githooks or mod events. It grows to every hook and setting with a "runs
  on" column (Mac, Windows, cloud), and the page's Status tab links it. Audit holes to close: H1 GitHub
  MCP writes never reach the guard (settings.json matcher; fixed in stage 1). H2 unarmed clones commit
  env files; H3 hooks fail open on a partial install. H4 a repo's disableAllHooks is unwatched; H5 no rm
  shim on Windows; H6 decision watch desktop-only. Page questions: ArtifactData writes run the same
  question form (guard.py) and judge (call_judge.py, past rulings included) as the chat box. Home:
  decision hook-catalog-page.

Coordinator 13:00 CST Nov 11: a long cloud session keeps the hooks installed at its start. Its copy
lacked lane-effort-pin (10e38b0ae, 13:40 CST Nov 10) until a reinstall at 12:50 CST Nov 11, so 7 of 7
lanes read started with a bare "/effort medium" and the brief came later. Owner 12:59 CST: "its weird
a lane can be spawned without its brief first preprovided". A session whose installed hooks are older
than main says so at its next turn and reinstalls; the fresh start clears it once.
Owner 13:10 CST: "maybe we enforce cloud sessions to restart often mechanically based on certain
conditions like certain items landing on main". Read 13:11 CST (decision idle-resume-compacts): the
cloud reruns the install at each worker restart, which follows an idle gap. A busy session never
restarts, so only it goes stale. Owner 13:21 CST: "yes sorry i meant reinstall not restart i agree".
When hooks or settings on main
changed since the install, the session reinstalls at its next turn, in place, with no restart. It
restarts only for a change a reinstall cannot load. Whether a new hook entry in settings.json loads
without a restart is unmeasured; a lane measures it first.

### 3.11 One override route, with a receipt

- **R12.** Owner 16:10 CST Nov 10: "yes this statement of opus 4h etc also feels super arbitrary". And: "i dont
  want to do such rigid word grants moreso like if i say send a swarm of opus agents that just works too
  yanno? A is good though but it should be override <anytime> or override not just override and
  override 4h". One route reads the owner's own typed words for overrides and Opus asks alike, judged
  and fail closed. Agent or pasted text never grants, except a relay in R18 point 5's form (owner 09:10
  CST Nov 11, below). Fast path, no model call: `override` (one act) or
  `override` with any length (15, 15m, 90 minutes, 2 hours, 4h). Any other wording is judged. Every
  grant prints one receipt line the owner sees (what it lifts, one act or until when); today a grant
  prints nothing. A refusal no override can lift says so. Departs from: decision owner-override, where
  a longer phrase such as "override 15m please" grants nothing; under R12 the judge reads it. Home:
  decision owner-override, rewritten in place.
  An override may travel by relay. Owner 09:10 CST Nov 11, in the coordinator's chat, to the question
  "may an override travel by relay?": "q1 -- yes". A relay counts only in R18 point 5's form: his exact
  words, their time, and the one session and act they cover, checked against the sender's feedback log.
  The receiving session prints the same receipt line. Until R18 point 5's check is built (stage 4), only
  his typed words and a page save grant an override. This changes decision owner-override's sentence
  "An override covers only the session where the owner typed it": a relay in that form reaches the
  one session it names.

### 3.12 A lane never stalls on a popup

After 3.11, because its third part uses the same owner grant route.

- **R13.** Owner 16:16 CST Nov 10: "I need it to be that lanes that coordinator spawns are either A)
  banned from ever having any sort of popup / request that interrupts them, or B) in the artifact i get
  hyperlinks to those sessions that then show me their erequest and clear them -- I strongly lean
  towards A though"; 16:17 CST: "trying to make sure u dont misunderstand this into opening a large
  hole"; 16:18 CST: "yes" to the form. Outcome: a popup inside a lane is a stall the owner cannot see,
  which costs speed and buys no accuracy. Every popup becomes a refusal plus a routed question, never a
  silent allow, so safety stays the same or stricter.
  1. A lane never opens the question box: a guard refuses it in any session with a parent. The lane
     sends the question to its parent, triage puts it on the page, and the lane keeps working on what
     does not depend on it, or ends its turn.
  2. A lane starts in a mode where an act not pre-allowed is refused, not asked; the refused act goes to
     the parent like a question. A builder first confirms the cloud `dontAsk` mode refuses rather than
     prompts (unverified).
  3. An act that needs the owner's typed word (an override, a guarded settings write) becomes a page
     item; his save on the page is the grant (skill waiting-page). A relay in R18 point 5's form also
     grants it (R12); any other agent text never grants.
  4. Cards no mode can stop (repository trust, computer folder, owner-approval cards): a guard refuses
     those tools in a lane, and the lane routes the act to its parent.
  Replaces CLAUDE.md questions-go-to-owner, "The started session may wait on it." Unmeasured: how often
  lanes have stalled on a popup so far. Home: CLAUDE.md questions-go-to-owner; decision
  questions-go-to-owner.
- **R21. A page write never asks.** Owner 19:01 CST Nov 10: "ive found repos in cloud sessions of
  triage of repos requesting for me to permit this when it should just always be allowed this needs to
  be fixed too". The card was "Allow Claude to use db write (claude-artifacts)?". Outcome: triage stalls
  on a card for an act that is always allowed, so the owner's answers wait. The hooks that judge a page
  write (call_judge.py, guard.py) still run, so no check is lost.
  1. Read on main, 19:02 CST: `settings.json` already allows `mcp__claude-artifacts__db_write` and the
     other page tools. The cloud card shows anyway. Owner 19:13 CST, a second card in a Degen session:
     "even this artifact write needed my permission". That card names the tool as `claude-artifacts:
     db write`, the allowed name, so a missing name is not the whole cause. Suspects: that session's
     settings lack the entry, or the card comes from claude.ai and no settings file can lift it.
     Owner 19:15 CST, a third card (home triage restoring its page, 18 writes): "only allow once for
     these". The card offers no "always allow", which points at the second suspect.
     Owner chat in the retrospective session, 19:27 CST, on home triage reloading its page: "so the triage session pulled it off [agents]
     which sskrf for permission on every repopulate and instead did it in batches of like hundred each
     but each batch still need my approvsl". And: "thats still not optimal". The card shows once per
     call even with `db_write` allowed. That session also showed two tool names the allow list lacks:
     `mcp__claude-artifacts__db_usage` and `mcp__claude-artifacts__read_artifact`. Auto mode rightly
     refused its try to write its own allow list.
  2. Until the fix lands, a page writer sends its writes in the main session, as `batch` calls of up to
     50 writes each, one card per call. It never writes the page from an agent.
  3. The page hooks match `ArtifactData` only, so they skip a write named `mcp__claude-artifacts__db_write`.
     Open PR #2549 (artifact-guard-matcher-names) adds those names. It lands with this fix.
  4. Owner 19:04 CST: "claude also added new artifact commands that start with db (surf the web) that
     im guessing we need to add too now to the allow list". `ArtifactData` now has nine actions: get,
     list, query, profiles, set, update, str_replace, delete, batch. The allow list names six tools.
     A web search found no public list of the new tool names.
  5. The fix lane first reproduces the card in a cloud session. It reads the real tool names from that
     session's tool listing, never from a guess. It then allows every page database action under each
     name the card checks. A test proves a page write in a cloud session shows no card.
- **D3. How much a lane writes (open).** Owner 16:46 CST Nov 10: "lane's own chat never reaches me
  anyway, pretty true -- but they do still type a whole fuckton of a lot, and that is tbd on whether we
  should have some sorta rules on how much a lane "chirps" in a snese". Open: measure lane output per
  turn first; a lane's only readers are its parent (the report) and its handoff.

Owner feedback 12:57 CST Nov 11 (relayed by the coordinator 13:00 CST): two background agents ended
with no hand-back, so their caller waited on nothing. An agent's end always reaches its caller.

### 3.13 Express pass for prose

- **R7.** Owner 14:12 CST Nov 10: "if we develop some sorta express pass for the entirety of prose to be
  fast to review i'd be open to considering that"; 15:22 CST: "this is very key yes". A PR whose owner
  quotes match the feedback log word for word skips the review round that decision
  docs-only-prs-skip-review (item 205 b, 2026-11-04) gives a record filing an owner ruling. First user:
  the follow-up plan PR. Home: decision docs-only-prs-skip-review, rewritten in place.

### 3.14 Prose stores tend themselves

R28 sets the order: the shared contract first (R27 is its first user), then the deeper audit,
then R29.

- **R27. The feedback log tends itself.** Owner 10:16 CST Nov 11: "this should've been a trigger for
  something that should've been mechanizable remember, we can't have sesisons fualting themselves for
  something that could bve cvorrected?" and "it seems like basically this was a good idea but it's
  execution was a little half baked in that it's never cleaned up after or tended to?". Case: the Stop
  check asked this session to keep 17 settled items in its handoff. Its remedy named only "put them in
  the handoff", never "mark [closed]". So the session copied ids to pass the check. Measured 10:17 CST in
  this session's log: 126 items, 57 rulings and 9 standing items still open, none closed by a tool.
  1. A ruling or task item closes itself when its home holds it on main. The Stop check already proves
     the home; it marks the line [closed] in the same rewrite that marks repeats.
  2. Each refusal of the check names [closed] as a way out, beside the handoff (R24).
  3. The compaction reminder lists only items that still need work.
  4. Owner words that reach a session by the question box or by relay are saved like a typed message.
  Home: decision owner-feedback-inbox. Runs with R16, which files a told mistake as a missing guard.
- **R28. Every prose store is tended one shared way.** Owner 10:19 CST Nov 11: "everything that marks
  prose should share the same "tending" mechanism ... it should be more uniform, standardized, and
  shared as much as possible to avoid stale duplication and to ensure shared best practrices". Stores:
  decisions, rules, docs and README, debts, handoffs, the feedback log, the roadmap and queue. Owner 11:39 CST
  Nov 11 adds the git copies of each repo's page and the mailbox: "i agree the fix is in r28". Case:
  claude-settings' copy fell about 11 h behind its live page (read 11:30 CST); the copy step and the
  Stop check both missed (triage, 11:39 CST). A copy's "still true?" test compares it with its live
  source. Step waiting-export-miss-cloud fixes the check. Audit 11:40 CST: degen, home and
  mailaudit copies 35-40 h old, banchi 5 days; q_max, joyous and ios-adblock have no copy. Owner
  11:45 CST: "is the live page being used correctly then if the data in there needs to be manually
  copied in and out? i figured it's just temporally same as with git? it feels weird that it's
  partitioned steps". Decision waiting-data-in-repo rules git the home and the page a view, but
  today sessions and the owner write the page first and git copies it later. The design pass makes
  git the first write, and names how an owner answer reaches git with no session awake. Owner
  11:50 CST: "ya if anything the actual page gets its database disableed if that's possible and then
  it's never an issue ... remember ij just care about the outcomes not the plumbing to reach it". The
  outcome: one store, no copy step, no lag; the design pass picks the route. Read 11:52 CST: a page can
  call the viewer's claude.ai connectors (capability mcp), the built-in Claude Code Remote one included.
  So an answer can wake its writer today. This account has no GitHub connector, so a page cannot write
  git directly yet. The other account is unread. Owner 11:55 CST: "The fallback is moving off artifacts to your own
  site ... this doesnt sound so bad tho tbh" and "maybe a PAT or a github API resolves this and we just
  go via that?". A token must never sit in a page: every viewer can read the page and its data. So a
  token route is a small server that holds it, such as a Cloudflare Worker that writes git through the
  GitHub API. That is the own-site route, now a full option beside the other two. Box
  answer before 10:22 CST: "i think a skim audit just for some overarching context and to avoid common
  pitfalls is best .. thetn shared/log-fix, then a deeper audit". Order:
  1. A read-only skim audit of how each store is tended now (started before 10:22 CST).
  2. A design pass sets one shared contract in lint/layout.json: per store, the item shape, a "still
     true?" test, and a close step. One runner calls it from points that already run: the merge
     check, the Stop hooks, compaction and triage status. No new timer or process. R27 is its first
     user.
  3. A deeper audit, then each other store moves over when a lane next touches it.
  Home: a new decision for the shared contract; R27's step waits on step 2.
- **R29. One job, one shared home, across all repos.** Owner 10:22 CST Nov 11: "it would be optimal if
  something identified shared savings opportunities like this in a sense across my repos
  retroactively and proactively". Answer 10:24 CST: "A" (file it after R28's deeper audit). Today
  lint/find_copies.py finds only word-for-word copies of this repo's files, and only in the compliance
  check; the plan refuter reads only its own repo.
  1. Looking back: at each compliance check, a meaning match finds the same job built twice across
     repos. Each find goes to this repo's triage as a candidate for one shared home.
  2. Looking ahead: the plan refuter asks "does this job already exist?" before a build starts.
  3. Both read one list of jobs and their homes.
  It reuses R28's deeper-audit way of reading stores. It adds no new process. The cross-repo read needs a
  session on the owner's computer, or each repo attached to a cloud session. Starts after R28 step 3.

### 3.15 Spend fewer tokens, measured first

Owner 11:55 CST Nov 11: "spend should also be logged if literally free to do so since it gives us more
data about how we do things". get_session already returns each session's cost (unmeasured; decision
spend-log-per-batch). The log is kept only if its reads are literally free, which is also unmeasured.
If they are, the batch runner reads the cost at each batch merge, a process already running, and
writes one line per session to the record branch. Readers: R33's model evaluation and the spend row of R34's tab. No timer, no new process.

Owner 13:10 CST Nov 11: "we need to figure out how to avoid container restarts for long running
sessions (keep them warm)". Read 13:11 CST (chatter audit; decision idle-resume-compacts): the cost is
not the restart, which adds about 4,000 tokens. It is the prompt cache, which expires after an hour
idle. The next wake then rewrites the whole context, about 200K tokens for a lane. Owner 13:20 CST:
"i banned stuff that seemed buggy from anthropic and that it was never supposed to be a llarger
permanent hard ban". Read 13:21 CST: the words "never on a timer" came in commit b25883784 (Oct 22),
whose stated reason is "watching must cost less than what it watches (owner, 2026-10-21)". A
keep-warm ping is not watching, and by that reason it passes. Prices (claude-api skill): a 1-hour
cache write costs 2x input; a cache read costs $0.20 per million on Opus 5.5 and $0.10 on Sonnet 5.5,
which is 1/40 of the write. So a ping every 55 minutes costs less than one rewrite for any idle gap
under about 40 hours. Unmeasured: what our Stop hooks and judges add to each ping. Owner 13:22 CST:
"A on keeping sessions warm too".
  1. Rule outcomes-mechanize-rules keeps its reason and drops the blanket "never on a timer": a timer
     is allowed when its record shows it costs less than it saves.
  2. A standing session sets a one-time check-in 55 minutes after its last turn, while it expects
     another wake within 40 hours. A lane whose PR merged is archived at once instead.
  3. One night on one standing session measures the ping cost, hooks included, before it spreads.

- **R32. A token audit, then cuts.** Owner 10:57 CST Nov 11: "i also wonder when the coordinator spawns
  lanes if there's ways to be more token efficient (here, and elsewhere tbh -- worried i overuse tokens
  in some ways)". Box answer 11:02 CST: "Audit now". Measured 10:58 CST from each session's totals: the
  coordinator (Opus, since Nov 3) spent $1,838 and runs at 349k of 500k context; it compacts at 442k.
  One small lane spent $8.31. Every turn re-reads the whole context, so a large context times many
  wakes is the likely biggest cost (unmeasured). A read-only audit (started by 11:03 CST) splits spend by
  session role and by source: context per turn, wakes, text loaded every turn, and hook judges. It also
  checks why lanes show a bare "/effort medium" first message (owner 11:02 CST: "the first message in
  cloud sessions spawns is often just "/effort medium" and then they get messaged their brief rather
  htan it being preloaded"), against decision agent-model-cap, which sets effort by the start call and
  sends the brief as the first message. The cuts are ruled on its report. Home: decision
  agent-model-cap.
  First report, 11:10 CST: partial, because agents have no session tools. Owner box answer 11:12 CST:
  "given my spend says i spent like thousands of dollars on like nov 8 -- i feel like u didn't properly
  catch where all my spend has gone. also remember, dollar savings shouldn't come at the cost of speed
  -- speed is more important (but it's all relative and not absolute)", and "Finish measuring first".
  So: a read-only measuring session (Sonnet, started 11:13 CST) sums spend by day, role, repo and
  model over every session. No cut is ruled before it reports. A cut that slows work is weighed
  against the speed it costs, and speed wins a close call.
  Measured 11:17 CST (800 sessions back to Nov 3; costs are each session's whole life): sessions
  active Nov 7-9 cost at least $22,075. Opus lanes, all started before the Sonnet lane ruling (owner
  2026-11-08 12:21 CST), are $19,889 of it, 387 lanes; no Opus lane started after it. Cost per lane:
  Opus median $22.9, mean $51.4; Sonnet median $11.9, mean $16.1. Lane life, start to archive: Opus
  median 64 h, Sonnet 28 h. Standing sessions, both Opus and missed by that listing: coordinator
  $1,839 and triage $1,567 since Nov 3. Not seen: hook judges, local sessions, the other account.
  The cuts, owner 11:21 and 11:23 CST Nov 11 (waiting page item 506):
  1. d with a. The coordinator and triage get a measured Sonnet trial inside R33's evaluation. "a: i
     agree fold into d": earlier compaction is set per model, so Opus can compact tighter than Sonnet, through the
     per-model key `modelSettings.<model>.autoCompactWindow` (decision precompact-handoff, rule 1).
     Owner: "opus could compact tigheter than sonnet no?". Yes; that key sets it per model. Why the
     coordinator compacts at 441,600 and seeded sessions at 384,000 is still unmeasured; the step finds
     the setting that causes it.
  2. b. Owner: "it seems like what we have planned fixes this already? ... it saves time and money no?".
     Mostly: R24 (each refusal names a working way out), R27 (feedback items close themselves) and the
     guard cull (3.6) cover most repeats. Two parts are new: all end-of-turn checks speak in one merged
     message, so one fix turn answers them all. And the hook drafts the "Recovered" and "Handoff gave"
     lines after a compaction, so they are not retyped after a refusal.
  3. c. A check-in that waits on CI waits at most 55 minutes, so a wake stays inside the prompt cache.
     It changes rule git-ci-wait-checks-in ("each wider apart") to "each wider apart, never past 55
     minutes". Owner: "we should keep some sort of tabs on how anthropic determiines warm cash so this
     doesn't go stale". The cap is read from one constant that names its source: the cache lifetime in
     Claude Code's docs, which this session's own system text gives as 1 hour, and 5 minutes once usage
     enters overage. That constant is a dated claim under R28's shared upkeep, so a docs change is
     caught.
  Compaction, owner 11:09 CST: "i frankly dont mind compacting sooner given we have such good handoff
  hooks". Today the coordinator compacts at 441,600 tokens and lanes at 384,000; why they differ is
  unmeasured (decision idle-resume-compacts). Cut 1 below sets the size per model from measured per-turn cost,
  so Opus can compact tighter than Sonnet (owner 11:23 CST: "opus could compact tigheter than sonnet no?"). The lever is the per-model key or
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, never `/autocompact` (decision precompact-handoff, rule 1,
  coordinator pick 2026-11-01 17:45). Decision idle-resume-compacts, which lists `/autocompact` as a
  cloud lever, is rewritten to match. Home: decision precompact-handoff, rule 1.

- **R36. Agents write little that no one reads.** Owner 12:49 CST Nov 11: "how much should our
  [agents] be allowed to just "type"". 12:52 CST: "im assuming the brief kinda needs to have a line in
  terms of how much to talk ... keep verbiage to a minimum something like that? or it's mechanized?
  unsure i'm deferring to you". Pick, under that deferral: the line goes in
  each agent role file and the lane start text, which load on their own, never in each brief. Briefs
  carry only task facts. A check proves each role file holds the line. Reasoning and tool inputs are
  never cut. The brief audit (started 12:48 CST) measures brief length and the narration share of lane
  output first; the line ships if narration is a real share. Measured 13:06 CST (read-only audit,
  scratchpad chatter-audit.md): narration plus final reply is 19-32% of visible output in standing
  sessions and 9% in a lane, so the line ships. It cuts context growth more than money: cache reads
  dominate cost. Each wake of an idle lane re-wrote about 200K tokens of cache for a short answer; that
  goes to 3.15. Owner 13:10 CST: "how to keep their prose from staying tight (maybe in their
  claude.md or mechanically idk or a judge that scans and says hey you yappin too much)". The reply
  judge gains one item: a reply longer than its reader needs, judged by who reads it, never by a word
  count (R37). It flags and never refuses. Home: agents/*.md; decisions agent-model-cap and
  reply-judge-samples-never-refuses.

- **R38. The repeat judge skips its own thread and marks without blocking.** Read 13:00 CST Nov 11:
  decision owner-feedback-inbox, Repeats (owner 2026-11-01 17:57 CST, "a model's meaning match, no
  glossary") made 8 marks today, 0 true. Two causes: one candidate is given to every item in a Stop, and
  a session's follow-up items match its own earlier items on the same owner message. Owner 13:03 CST:
  "yes on the fix !".
  1. The judge skips a candidate on the item's own home or the same owner message.
  2. Each item gets its own candidates.
  3. A mark prints one line and never blocks the turn.
  The meaning match stays, so a repeat in other words (the carousel and wheel incident) is still caught.
  Home: decision owner-feedback-inbox, Repeats, rewritten in place.

- **R39. A past ruling is challenged, never deferred to.** Owner 13:10 CST Nov 11: "yes on r39". Owner
  13:01 CST Nov 11: "my rules are to be challenged/questioned and never read as absolutes given im
  imperfect". Owner 13:03 CST: "how can we fix the defference in claude.md or whever it is taht's
  causing it". Read 13:04 CST: the past-ruling check (hooks/call_judge.py, item 8; hooks/question_form.py,
  "the owner is never asked twice") refuses any question on a settled point. Its only pass is a
  `Based on (ruling)` line, read as "a re-ask the ruling allows". It cannot tell a nag from a challenge,
  so sessions learn to defer.
  1. Item 8 refuses a re-ask with no new fact. It passes a challenge: the record and its sentence, a
     measure, the outcome it protected and what protects it now, and a proposed fix.
  2. Its refusal text says how to challenge, not to withdraw.
  3. The question form's Problem line names the act the yes gates, not the owner's authority.
  4. A red case: a challenge with a measure passes; the same question with no new fact is refused.
  5. Owner 13:04 CST: "maybe the judge hooks that run on our sesisons should identify it frankly just
     like how it identifies when shared mistakes and other stuff happens". The reply judge gains one
     item: a reply that names a flaw in a ruling but leaves it to the owner's authority, with no measure
     or fix. It flags, like its other items, and never refuses.
  Home: decision question-form; decision reply-judge-samples-never-refuses; rule
  outcomes-stale-decision-protocol.

- **R44. Child repos follow claude-settings, with cited exceptions only.** Owner 14:05 CST Nov 11: "on
  r44 yea agreed A build all 3". Owner 13:57 CST Nov 11: "i don't want it to be that the repoos like Q_max have
  adopted a ton of old rules and they just stick in them and claude-settings comes and is unable to
  bring that lift immediately". Read 13:58 CST: the mandate exists (decision session-tiers, Child
  repos, owner 2026-11-02 14:02 CST: a child contradicts a parent line only where it cites it as a
  known exemption, with the owner's grant). What enforces it: probe group restates catches copied
  record text only; skill compliance-check runs only when asked; claude-settings actions in child CI
  are pinned and move only when a session notices (decision action-pins-follow-sessions, which names
  seven pins that drift unseen). That decision's "no bot, no schedule" leaned on the timer ban that
  3.15 relaxed. Nothing flags a child line that contradicts a parent rule without an exemption.
  Step child-repo-gap ("Check how far each child repo is from claude-settings main") has been todo since
  Oct 29 with no lane; R44 folds into it.
  Owner 14:03 CST: "audits feel more like one-timey than they are mechanical ... i'd allow for example
  one quick scan of a part of q_max". Scan 14:04 CST (q_max 32d4373, CLAUDE.md and workflow pins): its
  CLAUDE.md cites the parent by rule id, as it should. All 9 claude-settings action pins sit at
  2ac382cc6 (Nov 8 20:50 CST), 2758 commits behind main, with 50 commits to actions/ since. Its records
  D-499 and D-833 make the pinned STE sentence-length lint its own law ("npm run lint runs the same
  lint, at the same pinned commit"), so R37's retirement of that cap will not reach q_max. Its own
  exception, D-705 (merge over a red browser.yml run, owner 2026-11-07 13:13 CST), cites a grant with a
  time but not the parent rule it departs from.
  1. Child CI runs claude-settings actions from the stable branch of R42 part 2, not a commit pin, so
     each tested change reaches every child at once.
  2. The split: skill compliance-check is the one-time sweep that brings a repo in line; a check
     in child CI keeps it there. The check flags a contradicting line with no exemption line, and pins
     move when claude-settings main changes an action.
  3. shiv-stylisms content (are its 23 rules still right) joins R35's review, which the owner signs.

- **R43. A usage brake on accounts with a rate limit.** Owner 13:48 CST Nov 11: "it might just be
  somehow local in my mac's coordinators handoffs and not on claude-settings anywhere but ya it was
  basically just that after usage hits 90% everything looks to gently wind down and 94% is a hard
  brake". Read 13:49 CST: no record, hook or page item holds it; page item 169 cites his Nov 1 17:56 CST
  ruling "no usage limit; a standing session runs until autocompact", which is about session length.
  Reading, for him to correct: at 90% of an account's 5-hour or weekly limit, no new lane or agent
  starts and running work finishes and writes its handoff; at 94%, every session stops new work. An
  account with no limit never brakes. First a lane measures whether a hook can read the percentages.
  Home: a new decision record, usage-brake.

- **R42. Rulings get acted on, and main moves the way Anthropic moves its own.** Owner 13:39 CST Nov 11: "a report is still just a report yanno that's something for
  me to read rather than something to act upon". Read 13:41 CST: Anthropic's post "Redesigning source
  control at Anthropic" (Oct 13, updated Oct 15) says "A proper merge queue, for example, doesn't make
  much sense at agent scale". It tests after merge and before deploy, with automated bisect and revert.
  Its Claude Code team scales human approval by the change's risk and tracks reverts as the guard; a
  webinar on it runs Nov 18. Our batch flow held a lock on main during each batch run (rule
  git-no-merge-during-batch-ci, retired by the per-lane cutover; its replacement is git-red-main-reverts), and the baseline counts 147 lane drops in 15 batch merges.
  1. A step that holds an owner ruling and has no lane is the coordinator's queue. It starts the step
     under rule parallelism-keep-going, not as a report line. Triage's reply names the step, and the
     sender's log item points to it, so the feedback guard proves it exists.
  2. Proposed for stage 3, after a Plan agent and a refuter: a lane merges on its own green checks and
     its review, sized by risk. Main's CI runs after the merge; a red run bisects and reverts the
     breaking commit. Sessions install from a stable branch that moves only when main is green.
  3. Guard numbers: reverts per merge, and the pace numbers. Main must first finish a CI run (#2591).
  Owner 13:43 CST: "lanes compete more for the machine isn't a real problem on cloud sessions where each
  spawns its own machine right? and then it is true for local machines though (which is why we have
  load brakes for local right" and "r42 part 2: i'm pretty open to this radical approach -- A". Part 1
  stands on his 13:39 "A seems fine". Shared limits remain: the account's rate limit, CI runners, and
  agents inside one cloud container. The Plan agent's design for part 2 comes back to him.
  Coordinator 13:51 CST: 70 ruled steps have no lane; the freeze (owner 09:18 CST Nov 10) allows fixes
  of items on main. Owner 13:50 CST: "remember my goal was to just have main in a state where it's
  stable enough to take on the full load of 70+ asks at once like my priority is max outcome speed".
  Owner 13:51 CST: "a". The freeze narrows: until the fan-out, only fixes that main's stability needs
  start (#2591, the mailbox fix, and failures in main's first finished run). Every other ruled step,
  fixes included, starts after the guard test file split, all at once.

- **R41. Mods, skills and the output style: keep all, fix seven defects.** Owner 13:36 CST Nov 11:
  "r41 yes on all". Owner 13:25 CST Nov 11: "tell me how my mods and skills work ... are they even good to keep
  around anymore, are they under the right folders/locations". Read 13:33 CST (two read-only audits,
  scratchpad mods-skills-audit.md and decision-watch-audit.md): all 5 mods, 11 skills and shiv-stylisms
  are in the right folders and earn their place. Decision watch runs in cloud too (167 turns logged in
  this session).
  1. When the given path fails, decision watch finds the transcript by session id. Its UNKNOWN names
     the path and shows once per session, and so does the silent "no transcript" case. Red cases first:
     Windows backslash, drive letter, `~`, Git Bash `/c/`, a second config dir, a long folder name.
  2. The cloud installer skips `__pycache__` when it hashes a skill, so it stops backing up waiting-page
     at each start (23 copies, 38 MB here).
  3. waiting-page SKILL.md (883 lines) splits by topic and drops its PR history.
  4. The rule map counts the reply judge's four style rules; the 20-line hand-off bullet in
     shiv-stylisms splits.
  5. Decision question-form says what the code does: a Departs from line on every question.
  6. One stale note and the unused ponytail marketplace go.
  7. Owner 13:33 CST: "i also frankly dont see some mods that i do see on local claude like the
     weather context thing". His screenshot shows the weather band on a local session and none on this
     cloud one. The mods are installed here and their hooks run (decision watch logs each turn), so the
     gap is in the drawing. The plugin docs say a cloud session draws in no screen of its own. A lane
     reads the debug log of one cloud session to find whether the band hook runs and what the app drops.
     A platform limit goes in a record and upstream; a defect of ours gets fixed.
  Homes: decision decision-watch-mod-limits; install.sh; skills/waiting-page; lint/rule_mechanisms.json;
  decision question-form.

- **R40. Compaction trigger tested higher.** Read 13:05 CST Nov 11 (decision precompact-handoff, item 2):
  the cloud sets CLAUDE_AUTOCOMPACT_PCT_OVERRIDE per session, 80 here, so compaction starts at 384K of a
  480K window; one session ran at 92. Owner 13:21 CST: "compaction: A". After the fresh start, a lane
  sets 92 in the settings env and reads one new session's trigger with get_session. If our value wins,
  it holds everywhere; if not, the record says so. Home: decision precompact-handoff.

- **R37. No fixed word cap, and no "STE" name.** Owner 12:54 CST Nov 11: "i thought i eliminated all
  STE requirements from everywhere in the repo weeks ago (along with hard limits like 30 vs 31 words
  etc ...) given my disdain for hard arbitrary static numeric limits". Read 12:55 CST: decision
  plain-prose-lint keeps STE001, a CI error on a sentence over 30 words (max_words 30). The name
  survives in lint/ste_lint.py, actions/ste-lint, the STE0nn codes and rule anchor output-write-in-ste,
  against his 2026-11-02 13:22 CST ruling "drop Simplified Technical English (STE) as a named
  standard, everywhere". 73 of 3561 commits on main since Nov 4 fix the lint. Owner 12:56 CST: "A --
  and im sure this 30 word thing is only one of many stale digit level hooks".
  1. STE001 stops failing; wordiness and repetition go to reviewers and judges, which never count.
  2. The lint, its action, its codes and the rule anchor drop "STE" from their names.
  3. A read-only census (started 12:57 CST) lists every fixed number that refuses or fails. Each one
     the owner did not rule is retired, or derived from measured runs as in 3.2.
  Owner 13:10 CST: "on fixed numbers A". The census (scratchpad limits-census.md) lists about 45
  numbers; item 3 covers each one the owner did not rule. Two contradictions go in too: merge.py warns
  at 70% of a job cap where decision ci-job-caps says 80%, and bin/sim-lease refuses on load average,
  which decision machine-load-brake forbids.
  Home: decision plain-prose-lint, rewritten in place.

- **R35. The global CLAUDE.md loads only what each session needs.** Owner 12:38 CST Nov 11: "im
  wondering whether i properly keep claude.md's just at the repo level and claude-settings level as its
  parent and no where further". Read 12:39 CST: the levels are right (global, repo, path-scoped rules
  in .claude/rules). The global file holds 3,890 words on every turn of every repo, and its size check
  counts lines (108 of 200), not words. Owner 12:40 CST: "yes that's fine it would need my sign off (the
  actual results of the review) but just marking it as an item for review is good to dos onow".
  1. A read-only audit maps each global section to the repos and session roles where it matters.
  2. The owner signs off the results before any section moves.
  3. A lane moves the signed-off sections to path-scoped rules or skills, and the size check counts
     words too.
  Home: lint/check_claude_md_size.py; rule tokens-folder-rules-load-by-path.

## Stage 4. Make the roadmap and triage mechanical

- **R25. Stage 4 runs with stage 3.** Owner 09:20 CST Nov 11: "with stage 3, but i think we should in
  the planning stage itself maybe define how batches will be built". Stage 4's lanes start with the rest
  of stage 3, once 3.0 lands. How batches are built is settled before stage 3 starts (R26, item 3.4).

- **D1. The roadmap is mechanical (ruled g, 15:19 CST Nov 11).** Owner 14:14 CST Nov 10: "realistically we have the actual
  roadmap be mechanizable like the status/queue/asks/etc". Already ruled: decision stalled-steps (owner
  2026-11-06 11:39 and 2026-11-07 12:22 CST) says `doing` is derived from live work, and
  skills/roadmap/build.py prints each stalled step. Not in force: 135 of 396 "doing" steps point at
  archived sessions, and 292 were re-stamped by bulk passes on Nov 10. Owner 15:22 CST: "i think at
  that point we should just integrate github's pr tracker thing there's like a whole connector it has
  doesn't it it's kinda like a table that shows stuff in progress" (GitHub Projects, the table view).
  Settled by ruling g (owner 15:19 CST Nov 11, under R45): no Projects table; status comes from live PRs.
  The probe ran (owner 14:20 CST Nov 11: "a is cool given it's just a probe"): GraphQL is refused in the
  cloud, so the table cannot be written from there.
- **R6. Triage's outbox is read against main.** Owner 15:22 CST Nov 10: "yes but it's tbd if an outbox
  is the right spot right? but for rn it only make senses that it is read". A check, run when triage
  reports status, lists each owner ruling in the outbox and whether its home on main holds its words.
  Whether the outbox stays the place for rulings is open. Home: decision owner-feedback-inbox.
- **R18. One home and one wake per answer; a relay is easy and checked for carelessness.** Owner 16:46
  CST Nov 10: "I do think the process of what's being woken, and how to pass words along / relays needs
  to be vastly improved as the current process is broken/flawed"; 16:54 CST: "too many sessions seem too
  tapped in to the artifact like they'll be woken for any change to the artifact not just an update to
  their specific question"; 16:55 CST: "relayed grants need to come in more easily and more intuitively
  ... we never protect against maliciousness only carelessness/negligence", points 1-4 agreed; 16:57
  CST: "agreed yes -- but it should also be known by sessions how to carry my grant so that way it's not
  like problematic or a cause of pain".
  1. Only triage watches the page; a Send wakes triage alone.
  2. Each item names who wakes for it: the asker, plus any party it lists. Triage sends exactly those
     sessions one message (page link, item id, the pick); each reads its answer from the page.
  3. Each answer has one home, the page. A question goes only to the page; the chat holds one line, "on
     the page, item N". A hook moves a question with options from a reply onto the page and leaves that
     line, so it does not rest on the session remembering. An answer typed in chat goes onto the page at
     once.
  4. Never reply in a page comment thread; the item is rewritten instead (questions-go-to-owner, owner
     2026-10-28 02:44 CDT). A hook enforces it over the platform's own suggestion.
  5. A relay counts when it carries the owner's exact words, their time, and the one act they cover, in
     one form every session knows: `Grant: "<exact words>" (owner, <time>) covers <act>`. A guard in the
     sending session checks the words are in its own feedback log (catches a paraphrase, a widened act or
     a wrong item); the receiver acts with no page round-trip. A relay in another shape is refused with
     that form as the remedy. The page route stays. Per guard-guards-mistakes-only, no check assumes an
     attacker.
  Evidence (coordinator, 16:49 CST): 9 page comments today each carried two clashing relay
  instructions. A chat answer reached the page 4-9 min late and the notes hook refused 8 turns meanwhile.
  Every owner question was sent twice and the copies drift; the H1 grant reached the coordinator only by
  a chat relay. Cost: one hop through triage before the asker wakes (unmeasured). Home: skill
  waiting-page; decision relayed-grant-read-from-page, rewritten in place.
- **R19. Debts and notes are kept in place, like the roadmap.** Owner 17:00 CST Nov 10: "need to know
  if triage is properly reviewing and adjusting the debts and notes lists just like i have it adjust
  the roadmap/questions posted or i have all my sessions rewrite their handoff entirely in place rather
  than just append". And: "does this make sense? in general something like notes/debts probably should be
  visible from the artifact itself too"; 17:03 CST: "why it's so hard for AI to track the time"; 17:11
  CST: "approved".
  1. Owner item 358 lands first (sightings and expiry, one debt-fix lane per batch; step
     notes-sightings-expiry, PR #1619, not on main). It gives the 190 `Until:` lines a reader.
  2. Triage owns debts and notes as it owns the roadmap: its whole review at each batch merge merges
     families into one line, closes what is stale or past `Until:`, and rewrites the rest to what is
     true now.
  3. The page shows both: notes count, growth, oldest and largest families; the debt count fixed (today
     122 counts README.md and notes.md); the cull panel reads live numbers (today 47, from Oct 20).
  4. The writing tool stamps every page and roadmap time from the clock, never the model; a guard
     refuses a blank or unreadable time (step page-time-field-valid). Cause: about 190 blank times
     written Nov 10 from a misread clock tool, repaired by hand.
  Evidence (audit 17:06 CST, main 2d6f67f7c): notes.md 1,918 lines (504 KB), up 27% since Nov 7; 120
  debts. 24% of notes are over 14 days old; about 2% cite gone code, 2-3% repeat; no rule makes anyone
  review notes (CLAUDE.md roles-findings-are-debts-or-notes is filing only). Folds in roadmap steps
  c55 (re-weigh as a whole, notes stay short; owner Oct 26) and o8 (every debt and note on the page).
  Home: CLAUDE.md roles-findings-are-debts-or-notes; skill roadmap; docs/debts/README.md.
- **R22. A respawn rewrites every session id at once.** Owner 19:19 CST Nov 10, on home's move to a new
  account: "its moreso that a session ended coordinwtor and all and a new coordinator and sessions
  respawned and somehow no one rewrote the session ids to now be the new ones". Outcome: an answer
  wakes a dead session, and the owner has to ask who does the work.
  1. Cause (read on main): skill project-ops keeps the roster in the claude.ai project instructions,
     "so keep no second copy in the repo". No session can write there, so sessions copy ids into page
     items and briefs, and nothing rewrites those copies.
  2. The roster moves to the record branch, where triage writes it. The session that starts a standing
     session or lane sends triage the new id in the same turn. Triage rewrites that roster line.
  3. A page item, brief or handoff names a lane slug or role, never a session id (CLAUDE.md
     git-slug-then-claim-number already says so for lanes). The wake path reads the id from the roster
     when it sends. A guard refuses a page write that stores a session id.
  4. Fits R18 point 2: each item names who wakes, by slug or role.
  Home: skill project-ops; skill waiting-page.
- **R45. How cloud sessions delete branches.** Owner
  14:25 CST Nov 11: "im good with either an actions workflow or a github token -- github token seems
  better? im very ambivalent to tokens being in all my cloud sessions its just a github token".
  Measured 14:21 CST: the cloud relay drops a branch-delete push; a new-branch push works. Origin holds
  2,338 branches (331 under archive/), because a cloud archive push adds a branch and the delete fails.
  Probe github-projects-probe, 14:23 CST: the cloud cannot read or write GitHub Projects.
  1. The owner makes one GitHub token (repo and project scopes) and adds it to the cloud environment as
     SHIV_GITHUB_TOKEN.
  2. A session tests one branch delete and one Projects read with it. The relay, not GitHub, refuses
     today, so the test may fail.
  3. If the relay passes it, deletes go through one home that applies the Oct 30 grant (last commit on
     main or an archive branch), and the guard reads that route. If it refuses, the same token becomes a
     GitHub repository secret, and an Actions workflow does the deletes and the table on GitHub's side.
  Result, 15:04 CST: the relay refuses writes made with the owner's token too (REST ref delete 403, "Write
  access to this GitHub API path is not permitted through this proxy"; GraphQL 403). REST reads pass. So
  the fallback holds: an Actions workflow deletes with GitHub's own token, and the Projects table needs
  the owner's token as a repository secret.
  Ruled g, owner 15:19 CST Nov 11: "i think my answer is G right -- the table view isn't too releveant if we
  have other ways around it right?". 1. GitHub's auto-delete setting removes a merged PR's branch. 2. An
  Actions workflow with GitHub's own token deletes the rest the Oct 30 grant allows. 3. A check derives each
  roadmap step's status from live PRs on the roadmap branch; no Projects table. The owner's token is not
  needed. The docs say the relay blocks deletes, tags and GraphQL for every token; only a self-hosted
  environment skips the relay.
  Scope ruled k, owner 15:31 CST Nov 11: "sure k is fine". One shared branch-sweep action in claude-settings,
  called from each repo's existing CI at each push to main, with that repo's own token; the R44 child-repo
  sweep adds the call. Auto-delete of merged PR branches is on in all 8 shivinate7 repos and all 7
  ssemwal-cdc repos (owner's gh runs, 15:26 and 15:31 CST).
  Rulesets, ruled r, owner 16:43 CST Nov 11: "r". In the R44 child-repo sweep, a session on the owner's
  computer moves every repo's main to a ruleset that requires only all-jobs-passed and blocks deletion
  and force-push of main. Cause: a classic rule with many checks failed to save (owner, 16:39 CST). Owner 16:49 CST, in the coordinator's chat (coordinator-relayed): "yes
  with bypass": the ruleset may also let the repository admin role skip the checks on pull requests only. The
  grant names rulesets, so it lands in the repo's standing grants beside the Oct 30 grant (draft
  PR #2606). The merge tool reads rulesets, ruled c, owner 19:49 CST Nov 11: "c is prob best".
  Today merge/merge.py protection_names reads main's old branch protection and stops every merge when it
  is gone. Step merge-reads-ruleset makes it read main's ruleset first and the old protection second;
  skills/project-ops/scripts/protect.py, which sets classic protection today, will set the ruleset. It lands before the sweep removes any old
  protection. Once every repo has a ruleset, the old-protection read is deleted. Option c carried the label
  "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo"; he
  chose it over that ruling.
  No GitHub Issues, ruled p', owner 16:44 CST Nov 11: "agreed on p", then "yea" when asked whether he meant
  the refuter's revised p'. g is
  mostly built: skills/roadmap/build.py derives live and done from PRs (decision stalled-steps). 1. Nobody
  types doing; triage's build sets status from live PRs. 2. Triage closes the stale drafts on build.py's
  list once, then at each batch. 3. A guard refuses a lane PR whose branch or title names no step id
  (45 of the newest 100 open PRs named one by branch).
  Home: decision for the delete route (new); D1 for the table.

- **R34. The page shows how the system works and how healthy each part is.** Owner 11:35 CST Nov 11:
  "i more or less don't understand what i've built and how well built it is as i care about how it
  acts in the front end but there's a fuckton of backend". 11:39 CST: "yes i think build it -- let me
  know if that should be part of the standing artifact or no". G14 makes the page one page, so this is
  a tab on claude-settings' page, not a new artifact. Each row names what the owner sees, what makes it
  happen (hooks, checks, skills, decisions), and how healthy it is, measured from git, CI, the debt
  store and guard logs. A part with no measure says "unknown".
  1. A read-only audit drafts the rows now.
  2. The owner judges the draft.
  2a. Owner 12:37 CST Nov 11 judged the 20-row draft: "it's not very pretty and i cant tell if its
     exhaustive, but for a temporal table i think it's fine as is for now". The draft stands.
  3. A lane builds the tab, with a designer first. R28's shared upkeep refreshes each number at
     triage status, with no new timer. A check proves the tab exhaustive: it lists each hook, check
     and skill that no row names.
  Home: skill roadmap (the page's tabs); docs/map/.

## Stage 5. Resume lanes

Under the new flow, once stage 3 and the settled parts of stage 4 land. An open part holds nothing: D1,
R6's open outbox question, and R19 point 1 (waits on PR #1619) land when they land. Then the rest of the
queue. Re-measure the baseline below.

## Dropped

- "89% of open steps work on this repo's own machinery". Owner 15:22 CST: "this repo's own machinery is
  basically every repo's own machinery though to be fair".

## Baseline, to judge the restart

Measured 2026-11-10; re-measure after stage 3.
- Batch lead time, first lane commit to merge: under 150 commits median 4.4 h (n=45); 150+ commits
  median 57.8 h (n=10). Batch 72: 2 d 21 h 43 min.
- Batches merged per day: Nov 5 13, Nov 6 12, Nov 7 17, Nov 8 6, Nov 9 8, Nov 10 3.
- PRs Nov 6-10: 1278 opened, 393 merged. Open at 13:20 CST: 709.
- Handoffs (478 sessions): 215 end waiting on the batch runner's merge; 139 name a rebase or main move;
  132 name a re-review after a head move.
- Batch CI (checks.yml, Nov 10): green n=4, 34-211 min, median 51.
- Batch flow, last 15 batch merges to 08:26 CST Nov 11 (256 lanes): 74 batch builds per 15 merges
  (R26 target: one CI run per batch); 22% of CI minutes on heads that merged; 147 lane drops; lane wait,
  last commit to merge, median 536 min.
- Each batch merge's report gives the four pace numbers (CLAUDE.md reports-batch-pace-numbers):
  wall-clock, lanes run and most at once, minutes with no lane running, brake refusals. Owner
  12:44 CST Nov 11: "how will we judge how well the parallelism is landing?" These numbers, against
  this baseline, are the answer.
