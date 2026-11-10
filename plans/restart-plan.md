# Restart plan: how claude-settings lands work after the freeze

Owner's plan, kept by the retrospective session (session_013NEJKz5AWFJhGvmCUoi6wQ, child of the
coordinator session_013NEJL2hB1pLZPDpzas7VgB). Rewritten in place each time a point settles; git keeps
the history.
Last rewrite: 2026-11-10 16:11 CST.

Judged by two priorities, in order: accurate, then as fast as possible without losing accuracy.

## The flow, in order

1. **Drain.** In progress (owner chat Nov 10, between 13:31 and 14:07 CST: "im drianing as we speak"). The freeze holds
   (owner 09:18 CST Nov 10): no new lanes except fixes of items landing on main.
   Freeze exception, owner 16:02 CST: "i see yes fix it then" - one lane makes the settings.json guard
   matcher route the GitHub MCP write tools to guard.py (audit hole H1, R11), with a test that every tool
   the guard judges is reached by the matcher.
2. **Land this plan on main.** One prose PR holds every settled ruling below in the owner's words with
   its time. It is the first PR after the drain. The express pass (R7, stage 5) would make
   this PR fast; until it lands, the PR takes the normal docs-only route.
3. **Change how every lane flows,** before any other lane starts. Each is one lane, in this order:
   0. One glossary of roles, the same on local and cloud (rulings G1-G14; step
      glossary-same-local-cloud). First because every later brief uses its terms.
   1. Checks that can refuse a merge run in CI (ruling R2).
   2. Time limits end hangs only (ruling R3). R2 and R3 together stop a green batch from being
      refused at merge.
   3. A review record survives a clean main merge (ruling R1).
   4. A batch closes on a limit (step batch-freeze-lane-set-enforce, already doing).
   5. Lane lint runs once per lane; batch CI fails fast (ruling R4).
   6. One cull of guards with recorded wrong refusals (ruling R5).
   7. One model table that every spawn, guard and check reads (ruling R8).
   8. One rounds record; round 3 and the net-value test per owner pick 471 a (ruling R9).
   9. A hook refusal asks for a short correction, never the whole reply again (ruling R10).
   10. One catalog of every hook and setting, with where each runs, linked from the page (ruling R11).
   11. One override route, read from the owner's own words, with a receipt (ruling R12).
4. **Make the roadmap and triage mechanical** (direction D1, open; ruling R6).
5. **Express pass for prose** (ruling R7). It can move before stage 2 so this plan's PR uses it.
6. **Resume lanes** under the new flow. Then the rest of the queue.

## Settled rulings

- **R1. A review record survives a clean main merge.** Owner 14:07 CST Nov 10: "i agree on letting it
  survive a clean merge where batch ci sees the problem rather than asecond review i agree it shd be
  mechanical tooo". A record stays valid when the new head differs from the reviewed head only by a
  clean merge of main, with the lane's own diff unchanged, proved by the merge tool (for example git
  range-diff). Any difference keeps today's rule. Batch CI catches clashes with main.
  Home: decision pr-review-record, rewritten in place. Folds in steps fix-check-after-main-merge and
  fix-check-chain.
- **R2. Checks that can refuse a merge run in CI.** Owner 14:07 CST Nov 10: "i agree speed
  maximization is a good idea". The merge tool only reads CI's verdict and checks the batch is current
  with main. The Retire check moves into CI. Cause: batch #2551 green in CI at 11:15 CST, refused at
  merge 11:50 CST by the Retire check's 600 s local limit; one full CI run lost.
  Home: decision debt-close-runs-retire; step retire-check-whole-suite; merge.readyChecks in
  decision lanes-run-no-full-ci-job.
- **R3. Time limits end hangs only.** Owner 14:09 CST Nov 10: "time limits as a rule make little to no
  sense when they feel arbitrary and are not outcomes related ... I understand keeping time limits at
  some point for letting hung tests end". Form accepted 14:10 CST ("yes, that three-part form matches
  what I meant"):
  1. Stop on silence, not total time: a run ends only after it prints nothing for a while.
  2. A stop reads "hung", never "failed": never red, never a merge refusal; retried once, then reported.
  3. A total-time limit that must stay (CI billing) comes from measured green runs each time, never a
     number stored in code.
  Replaces: merge/merge.py LINT_SECONDS 1200, lint/check_debt_retire.py TIMEOUT 600,
  hooks/mutate_guard.py and janitor/mutate_sweep.py 1200, lint/check_python_floor.py 300.
  Home: new decision time-limits-end-hangs-only; decision ci-job-caps rewritten to match.
  Details, owner 14:24 CST Nov 10 (answers to triage's four points):
  - A check that gives a verdict (lint, tests, Retire) stops on silence, reads "hung", retries once. Any
    other background command is only reported and keeps running (decision stall-watch). ("yes that's ok")
  - Every CI job keeps a total-time limit, computed from recent green runs by a script, generously
    large. Local tools use the silence stop only. ("it should be generously large maybe")
  - merge.deadlineMinutes is computed each time from the current CI limits; reaching it reads "CI still
    running", never a refusal. ("this needs to be a moving target")
  - The silence window is measured per tool from the longest gap between output lines in green runs.
  - Margins multiply, never add: "+5m is not as generous as like +1.5x".
  - A new CI job with no green runs: its nearest similar job's computed limit x1.5. If it hits that limit,
    it is flagged as misjudged and moves to the largest current job's computed limit x1.5. Owner 14:36
    CST: "b is probably fine for now, with some sorta flag that if it quickly fails that it was
    misjudged and it goes to largest current job x1.5"; 14:37 CST: "if it was just made and it then fails
    in its first run or two that's a sign it was misjudged". Replaces the stored 60 min in ci-job-caps.
  - A job stops being new after its first green run. The nearest similar job does the same kind of work
    (lint, test, mutation, build); with none, the largest current job x1.5. Owner 15:03 CST: "yes thats
    fine agreed".

- **R4. Lane lint runs once per lane; batch CI fails fast.** Owner 14:54 CST Nov 10: "is there no truly
  fast way that retains accuracy?"; 14:56 CST: "yes D is approved". Keep the lane lint run at hand-off
  (inside each lane, in parallel). Drop the runs at join and on the batch head. Batch CI runs lint first
  and cancels the rest of the run at once when lint goes red; the red files name the lane to drop.
  A builder first confirms that CI cancels on first failure and that each red lint maps to one lane.
  Home: decision lanes-run-no-full-ci-job, rewritten in place.

- **R5. One guard cull now, then notes only.** Owner 15:04 CST Nov 10: "i'd say option e works for now
  with a revisit maybe to threshold lanes if it turns out to be problematic". One cull lane in stage 3
  fixes or deletes each guard or check with a recorded wrong refusal (60 "false alarm" lines in
  docs/debts/notes.md). It fixes each one, and deletes it only when its wrong refusals cost more than the
  harm it stops (rule building-guard-needs-incident stays; owner 15:23 CST: "b ... this is fine"). The list also covers the lane pick guard's wrong fires and the
  Departs-from separator and Recovered-line fires (owner 15:18 CST: "A is fine -- but the coordinator
  probably has way more data on how hooks have been acting than your small sample size does"); the
  coordinator sends triage its record of hook fires for the same list. After it, wrong refusals are notes only. If they turn out
  to be a problem again, revisit a threshold (a guard with 3 recorded wrong refusals gets its own lane).
  Home: new decision cull-guard-wrong-refusals, beside cull-rules (triage branch cull-false-alarms-once;
  rulings-declare-kind allows one ruling per record).

- **R8. One model table.** Owner 15:44 CST Nov 10: "on #1 -- A seems best". The role table in decision
  agent-model-cap is the only home for each role's and round's model and effort. The spawn guard requires
  or fills in the row's model and effort (today it only permits them, guard.py:3783-3788, so a spawn with
  no model runs reviewer.md's Haiku). The merge tool checks the model that ran, not the record's text.
  Agent files, brief markers and checks read the table. Each model ruling lands in one lane that changes
  the table and every reader together. Cause: rulings 279 d, 439 and 444 a reached main 12-57 h late and
  in pieces; 359 a, 359 b, 289 and 295 a are not on main. Home: decision agent-model-cap.
- **R9. One rounds record; no round 3 after a pass.** Owner 15:44 CST Nov 10: "yeah i never wanted round 3
  if it passed earlier and was so confused to see that it was occuring"; "agreed A -- can look into the
  sonnet noise thing later". Fold the 15+ rounds rulings into one record. Round 1 runs on item 359 a's
  model (Sonnet for a guard or check change, the role's model otherwise). Fixes are verified per G5. Round
  3 follows owner pick 471 a (2026-11-09 23:39 CST, step review-state-guard-needs-round-3) as it stands: a
  guard or check change that passes round 1 is done; only one fixed under a fix check waits for round 3;
  the net-value test is only for an unclear case that cannot finish by the end of the rounds (the
  2026-10-15 "still unfinished" valve in hold-unsafe-after-round-3). Evidence: round 3
  found a failure 0 of 14+ times after a clean round 2; the net-value hold caught 6 real holes. Deferred:
  Sonnet round 1 for every logic change (Haiku round 1 fails 79% vs 38%; noise share unknown).
  Home: decision hold-unsafe-after-round-3; CLAUDE.md roles-review-cap-three and
  roles-third-round-steps-up rewritten.
- **R10. A hook refusal gets a short correction.** Owner 15:44 CST Nov 10: "i never want my hook to have
  one spew out the whole thing again after -- as i fixed long ago in how the done deviations inputneeded
  hook works, that should be viewed as a best practice for other hooks that make you regurgitate output
  again". guard-remedy-not-to-owner:177 already says "post only the corrected lines ... Never send the
  report again", but no refusal text says it. Each Stop-hook refusal ends with that line.
  Home: decision guard-remedy-not-to-owner.

- **R11. One catalog of every hook and setting.** Owner 16:00 CST Nov 10: "A -- but also i kinda meant how
  when questions reach triage, do the pre tool question use stuff run on it just like it would when
  uqestions used to come in line in the chats?". docs/catalog.md (lint/hook_catalog.py) lists all 36
  hooks but no permissions, autoMode rules, env, cloud-only allow rules, githooks or mod events. It
  grows to every hook and setting with a "runs on" column (Mac, Windows, cloud), and the page's Status
  tab links it. Audit holes to close: H1 GitHub MCP writes never reach the guard (settings.json matcher);
  H2 unarmed clones commit env files; H3 hooks fail open on a partial install; H4 a repo's
  disableAllHooks is unwatched; H5 no rm shim on Windows; H6 decision watch desktop-only.
  Page questions: ArtifactData writes run the same question form (guard.py) and judge (call_judge.py,
  past rulings included) as the chat box. Home: decision hook-catalog-page.

- **R12. One override route, with a receipt.** Owner 16:10 CST Nov 10: "yes this statement of opus 4h etc
  also feels super arbitrary i dont want to do such rigid word grants moreso like if i say send a swarm of
  opus agents that just works too yanno? A is good though but it should be override <anytime> or override
  not just override and override 4h". One route reads the owner's own typed words for overrides and Opus
  asks alike, judged and fail closed; agent or pasted text never grants. Fast path, no model call:
  `override` (one act) or `override` with any length (15, 15m, 90 minutes, 2 hours, 4h). Any other
  wording is judged. Every grant prints one receipt line the owner sees (what it lifts, one act or until
  when); today a grant prints nothing. A refusal no override can lift says so. Home: decision
  owner-override, rewritten in place.

- **G1. Who acts.** Owner 14:23 CST Nov 10: "the who is good, but i can make a grant or ruling, so can
  arbiter (marked as such, and a tier below)". Three kinds of actor: the owner, a session, an agent.
  The owner and an arbiter make grants and rulings. An arbiter's is marked as the arbiter's, ranks
  below the owner's, and the owner can overturn it. Today an arbiter makes rulings only
  (decision session-tiers, Arbiter); this adds grants. An arbiter's grants never include Opus (G13). Home: decision session-tiers, GLOSSARY.md.
- **G2. Session roles, the same on local and cloud: coordinator, triage, batch runner, lane, arbiter.**
  Owner 14:23 CST Nov 10: "coordinator approved", "batch runner yes agreed", "lane yes agreed but solo
  should be able to merge ideally like it can be a one stop shop sometimes", "this collapse feels good".
  Solo, one lane and lane session collapse into one role, lane. A lane the owner starts, with no
  coordinator above it, may merge its own PR under a merge grant. The terms shape, tier-as-separate-axis
  and orchestrator drop. Home: decision session-tiers, decision lanes-start-as-agents, GLOSSARY.md.
- **G3. Archiving.** Owner 14:29 CST Nov 10: "archiving as part of the batch runners responsibilities is
  approved, with the coordinator archiving the ones that it decides to spot (in general though i assume
  that with my rules on how PRs should close older prs sooner that would mean batch role has more
  exposure to superceded prs/sessions and will be able to archive them)". The batch runner archives each
  lane after its merge, and each lane whose PR was superseded. The coordinator archives a lane it
  decides to stop. Builds on owner 2026-11-06 11:38 CST (decision session-tiers).
- **G4. Plain names.** Owner 14:29 CST Nov 10: "check fix reviewer should be the name", "review log is
  fine", "feedback log is good too". 14:33 CST: "i meant let's call it the "check fix reviewer" (or find a
  better name that's cool too)"; 15:44 CST: "sure that's fine" to fix verifier. Fix check -> fix verifier (the reviewer that
  verifies one fix). Reason: "check" already names a lint, test or CI job in the glossary, so a name
  with "check" in it would clash. review record -> review log; the per-session inbox file -> feedback
  log. The mailbox keeps its name.
- **G5. Rounds are numbered by the review they answer.** Owner 14:29 CST Nov 10: "approved on fixing the
  naming trap on the rounds". The fix after review 1 is labelled "Fix for review 1", not "Round 2 of 3".
- **G6. One role proof, local and cloud.** Owner 14:29 CST Nov 10: "yes cloud tags can be optional
  agreed", "local sessions do have sesion id yes". A session proves its role from one roster both
  places read (the Standing sessions list on the roadmap branch); cloud tags become optional. Local
  sessions have a session id, so the split is chosen, not forced.
- **G7. Standing sessions compact, they are not replaced.** Owner 14:29 CST Nov 10: "both it and triage
  and stuff in general are no longer replaced they just compact graciously it's odd that the other
  prose still remained". Matches session-tiers:18 (owner 2026-11-01, item 109 b). Stale text to
  rewrite: session-tiers:81 (arbiter "rotated before it goes stale, like triage"), GLOSSARY.md:63
  ("Triage, batch runner and arbiter rotate"), skills/project-ops/SKILL.md:3 and :17. Rewrite approved,
  owner 14:32 CST ("agreed on the rewriting from g7").
- **G8. A wrong term gets a gentle correction.** Owner 14:30 CST Nov 10: "i often call things by the wrong
  terms sometimes and don't want that to result in confusion for claude and instead be met with strong
  pushback and a gentle correction"; form approved 14:32 CST ("agreed on g8"). Three cases: the word maps
  to one term: act, and add one line "You said X; the term is Y, which does Z". The word names the wrong
  session or role: one line saying whose job it is and why, then route it. The word fits two terms: ask
  before acting. Home: CLAUDE.md speak-one-name-per-thing and the output style's
  style-wrong-tier-one-line, rewritten in place.
- **G9. Triage always writes the waiting page.** Owner 14:32 CST Nov 10: "yea triage always writes the
  waiting page". Replaces the three definitions ("where triage runs", "a project with a triage thread",
  "when no triage lives").
- **G10. Roles are hats.** Owner 14:33 CST Nov 10: "yes hats model works". A role is a set of jobs. In a
  solo run one lane holds every role it needs: it writes its own page items as triage and merges its own
  PR as batch runner. How many sessions share the roles depends on the size of the run, never on local
  or cloud. A solo run the owner is watching asks in chat, and writes a page item only when it must
  wait on him while he is away.
- **G11. Topic 1 closes: one behaviour on local and cloud.** Owner 14:36 CST Nov 10: "agree on your
  proposed close on topic 1"; 14:37 CST: "yes it can be closed". Every split a rule chose is removed, so
  both places behave the same. A split the platform forces lives only inside the tool, never in a role's
  definition. Splits to remove in the glossary lane (stage 3.0): two tests for "cloud" in the code;
  guards that judge only one of start_session and create_session; the merge role file on the cloud only;
  the load brake on the owner's computer only; a lane the owner starts cannot merge on the cloud yet
  (docs/todo.md, "Let a solo session merge", owner 2026-11-02 14:02 CST). Deferred to a later build
  phase (owner 14:37 CST, "can be targeted after/later"): the details of forced splits, mainly a team
  that mixes local and cloud sessions while the mailbox bridge (MAILBOX_REPO) is off.
- **G12. A lane's behaviour follows the size of the work.** Owner 14:55 CST Nov 10: "yes A this is good".
  Any lane builds a short list of edits itself when nothing can run in parallel; otherwise it fans out to
  agents, whoever started it. Merges rules roles-solo-builds-short-edit-list and
  roles-orchestrator-never-builds. Home: CLAUDE.md, decision session-tiers.
- **G13. The arbiter is a decider only.** Owner 15:08 CST Nov 10: "isn't arbiter just a decider, why
  would it ever have subagents"; "yes" to the form. It makes rulings in its repo, one tier below the
  owner. It may start only read-only agents (Explore, refuter) to gather evidence. It builds nothing,
  starts no lanes, and grants no Opus. The arbiter session itself runs Opus (agent-model-cap:61).
  Rewrite session-tiers:81 ("a standing session and an orchestrator"). Home: decision session-tiers,
  GLOSSARY.md.
- **G14. The triage artifact is one page.** Owner 15:52 CST Nov 10: "when i say triage artifact i meant both
  given that they've merged into one (and if you thought otherwise that's a prose fault that needs
  correcting)". skills/roadmap/SKILL.md:6 says so; GLOSSARY.md has no row for it, and the roadmap skill's
  trigger words still say "roadmap page". One glossary row: page, the repo's one page that triage
  writes, holding the waiting items and the Status tab. "Roadmap page" retires. Home: GLOSSARY.md,
  decision questions-go-to-owner.

## Directions, not yet settled

- **D1. The roadmap is mechanical.** Owner 14:14 CST Nov 10: "realistically we have the actual roadmap
  be mechanizable like the status/queue/asks/etc". Already ruled: decision stalled-steps (owner
  2026-11-06 11:39 and 2026-11-07 12:22 CST) says `doing` is derived from live work, and
  skills/roadmap/build.py prints each stalled step. Not in force: 135 of 396 "doing" steps point at
  archived sessions, and 292 were re-stamped by bulk passes on Nov 10. Owner 15:22 CST: "i think at that
  point we should just integrate github's pr tracker thing there's like a whole connector it has doesn't
  it it's kinda like a table that shows stuff in progress" (GitHub Projects, the table view). Open: a
  probe confirms which connector or API can read and write it from local and cloud; this session has no
  Projects tool loaded (unverified whether the GitHub MCP server offers one).

## Settled after discussion

- **R6. Triage's outbox is read against main.** Owner 15:22 CST Nov 10: "yes but it's tbd if an outbox
  is the right spot right? but for rn it only make senses that it is read". A check, run when triage
  reports status, lists each owner ruling in the outbox and whether its home on main holds its words.
  Whether the outbox stays the place for rulings is open. Home: decision owner-feedback-inbox.
- **R7. Express pass for prose.** Owner 14:12 CST Nov 10: "if we develop some sorta express pass for the
  entirety of prose to be fast to review i'd be open to considering that"; 15:22 CST: "this is very key
  yes". A PR whose owner quotes match the feedback log word for word skips the review round that
  decision docs-only-prs-skip-review (item 205 b, 2026-11-04) gives a record filing an owner ruling.
  First user: this plan's own PR (stage 2). Home: decision docs-only-prs-skip-review, rewritten in place.

## Open topics, not yet discussed

- How many lanes start: the owner said in the same answer "the limit isn't the problem, it's how the limit
  batches that's the problem". Covered by stage 3.4 for now.
- Dropped: "89% of open steps work on this repo's own machinery". Owner 15:22 CST: "this repo's own
  machinery is basically every repo's own machinery though to be fair".

## Baseline, to judge the restart

Measured 2026-11-10; re-measure after stage 3.
- Batch lead time, first lane commit to merge: under 150 commits median 4.4 h (n=45); 150+ commits
  median 57.8 h (n=10). Batch 72: 2 d 21 h 43 min.
- Batches merged per day: Nov 5 13, Nov 6 12, Nov 7 17, Nov 8 6, Nov 9 8, Nov 10 3.
- PRs Nov 6-10: 1278 opened, 393 merged. Open at 13:20 CST: 709.
- Handoffs (478 sessions): 215 end waiting on the batch runner's merge; 139 name a rebase or main move;
  132 name a re-review after a head move.
- Batch CI (checks.yml, Nov 10): green n=4, 34-211 min, median 51.
