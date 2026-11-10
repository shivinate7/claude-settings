# Restart plan: how claude-settings lands work after the freeze

Owner's plan, kept by the retrospective session (session_013NEJKz5AWFJhGvmCUoi6wQ, child of the
coordinator session_013NEJL2hB1pLZPDpzas7VgB). Rewritten in place each time a point settles; git keeps
the history.
Last rewrite: 2026-11-10 14:41 CST.

Judged by two priorities, in order: accurate, then as fast as possible without losing accuracy.

## The flow, in order

1. **Drain.** In progress (owner chat Nov 10, between 13:31 and 14:07 CST: "im drianing as we speak"). The freeze holds
   (owner 09:18 CST Nov 10): no new lanes except fixes of items landing on main.
2. **Land this plan on main.** One prose PR holds every settled ruling below in the owner's words with
   its time. It is the first PR after the drain. Open: an express pass for prose (stage 5) would make
   this PR fast; until then it takes the normal docs-only route.
3. **Change how every lane flows,** before any other lane starts. Each is one lane, in this order:
   0. One glossary of roles, the same on local and cloud (rulings G1-G10; step
      glossary-same-local-cloud). First because every later brief uses its terms.
   1. Checks that can refuse a merge run in CI (ruling R2).
   2. Time limits end hangs only (ruling R3). R2 and R3 together stop a green batch from being
      refused at merge.
   3. A review record survives a clean main merge (ruling R1).
   4. A batch closes on a limit (step batch-freeze-lane-set-enforce, already doing).
4. **Make the roadmap and triage mechanical** (direction D1, D2; not yet settled).
5. **Express pass for prose** (direction D3; open).
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

- **G1. Who acts.** Owner 14:23 CST Nov 10: "the who is good, but i can make a grant or ruling, so can
  arbiter (marked as such, and a tier below)". Three kinds of actor: the owner, a session, an agent.
  The owner and an arbiter make grants and rulings. An arbiter's is marked as the arbiter's, ranks
  below the owner's, and the owner can overturn it. Today an arbiter makes rulings only
  (decision session-tiers, Arbiter); this adds grants. Home: decision session-tiers, GLOSSARY.md.
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
  better name that's cool too)". Picked under that leave: fix check -> fix verifier (the reviewer that
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

## Directions, not yet settled

- **D1. The roadmap is mechanical.** Owner 14:14 CST Nov 10: "realistically we have the actual roadmap
  be mechanizable like the status/queue/asks/etc". Read: a step's status is computed from facts (PR
  open or merged, session live or archived), not hand-written. Evidence: 135 of 396 "doing" steps
  point at archived sessions; 292 "doing" steps were re-stamped by bulk passes on Nov 10.
- **D2. Triage's review is mechanical.** Owner 14:12 CST Nov 10: "the review of triage ought to be
  mechanized, not that the draft prs become mechanized immediately". Read: a check, run when triage
  reports status, lists each outbox item and whether its home on main holds it. Evidence: 563 outbox
  notes, about 6% acted on; 14 of 16 owner-ruling notes have no match on main. Related: step
  coordinator-transcript-reconcile (one-time reconcile of rulings against main).
- **D3. Express pass for prose.** Owner 14:12 CST Nov 10: "if we develop some sorta express pass for
  the entirety of prose to be fast to review i'd be open to considering that". One idea: a PR that only
  adds owner words with their time is checked by machine against the inbox and merges without review.

## Glossary points still open (topic 1)

- Other local/cloud splits (15 found): two tests for "cloud" in the code; start_session vs
  create_session judged by different guards; send_message vs SendMessage with the mailbox bridge off;
  merge role file cloud-only; load brake local-only.
- A lane the owner starts cannot merge on the cloud yet: the merge tool's cloud confirm needs the
  batch-runner role (docs/todo.md, "Let a solo session merge", owner 2026-11-02 14:02 CST). G2 needs it.

## Open topics, not yet discussed

- How many lanes start: the owner said in the same answer "the limit isn't the problem, it's how the limit
  batches that's the problem". Covered by stage 3.4 for now.
- Lane lint runs three times per lane (hand-off, join, batch head) against
  roles-each-layer-proves-once.
- Guards with recorded false alarms: report guard 15, frozen-path 6, ask-alone 4, question-form 4,
  builder-test-edit 4 (counts of notes, not firings).
- About 89% of 746 open steps work on this repo's own merge, review and lint machinery (title
  inference).

## Baseline, to judge the restart

Measured 2026-11-10; re-measure after stage 3.
- Batch lead time, first lane commit to merge: under 150 commits median 4.4 h (n=45); 150+ commits
  median 57.8 h (n=10). Batch 72: 2 d 21 h 43 min.
- Batches merged per day: Nov 5 13, Nov 6 12, Nov 7 17, Nov 8 6, Nov 9 8, Nov 10 3.
- PRs Nov 6-10: 1278 opened, 393 merged. Open at 13:20 CST: 709.
- Handoffs (478 sessions): 215 end waiting on the batch runner's merge; 139 name a rebase or main move;
  132 name a re-review after a head move.
- Batch CI (checks.yml, Nov 10): green n=4, 34-211 min, median 51.
