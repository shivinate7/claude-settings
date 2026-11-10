# Restart plan: how claude-settings lands work after the freeze

Owner's plan, kept by the retrospective session (session_013NEJKz5AWFJhGvmCUoi6wQ, child of the
coordinator session_013NEJL2hB1pLZPDpzas7VgB). Rewritten in place each time a point settles; git keeps
the history.
Last rewrite: 2026-11-10 14:30 CST.

Judged by two priorities, in order: accurate, then as fast as possible without losing accuracy.

## The flow, in order

1. **Drain.** In progress (owner chat Nov 10, between 13:31 and 14:07 CST: "im drianing as we speak"). The freeze holds
   (owner 09:18 CST Nov 10): no new lanes except fixes of items landing on main.
2. **Land this plan on main.** One prose PR holds every settled ruling below in the owner's words with
   its time. It is the first PR after the drain. Open: an express pass for prose (stage 5) would make
   this PR fast; until then it takes the normal docs-only route.
3. **Change how every lane flows,** before any other lane starts. Each is one lane, in this order:
   0. One glossary of roles, the same on local and cloud (rulings G1-G3; step
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
- **G3. The batch runner archives lanes.** Already ruled (owner 2026-11-06 11:38 CST, decision
  session-tiers: "A is fine the batch runner keeps archiving more automatically"). Owner 14:23 CST
  Nov 10 asked who and why; the coordinator also needs a part. Open: who archives a lane that never
  merges (dropped, closed or abandoned).

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

- Owner 14:23 CST: "idk what fix check even is; idk what review record is; inbox either". Proposed plain
  names: fix check -> fix review; review record -> review log; the per-session inbox file -> feedback log
  (the mailbox keeps its name).
- The "Round N of 3" marker names the fix after round N-1 by the round it leads into. Proposed: number a
  fix by the review it answers.
- Page writer: three records define it three ways ("where triage runs", "a project with a triage
  thread", "when no triage lives"). Proposed: triage always writes the page.
- Tier proof: a session proves its role only by cloud tags (get_session); a local session has none.
  Proposed: one roster both read, the Standing sessions list on the roadmap branch's CLAUDE.md.
- Other local/cloud splits (15 found): two tests for "cloud" in the code; start_session vs
  create_session judged by different guards; send_message vs SendMessage with the mailbox bridge off;
  merge role file cloud-only; load brake local-only.

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
