# Restart plan: how claude-settings lands work after the freeze

Owner's plan, kept by the retrospective session (session_013NEJKz5AWFJhGvmCUoi6wQ, child of the
coordinator session_013NEJL2hB1pLZPDpzas7VgB). Rewritten in place each time a point settles; git keeps
the history.
Last rewrite: 2026-11-10 14:20 CST.

Judged by two priorities, in order: accurate, then as fast as possible without losing accuracy.

## The flow, in order

1. **Drain.** In progress (owner chat Nov 10, between 13:31 and 14:07 CST: "im drianing as we speak").
   The freeze holds (owner 09:18 CST Nov 10): no new lanes except fixes of items landing on main.
2. **Land this plan on main.** One prose PR holds every settled ruling below in the owner's words with
   its time. It is the first PR after the drain. Open: an express pass for prose (stage 5) would make
   this PR fast; until then it takes the normal docs-only route.
3. **Change how every lane flows,** before any other lane starts. Each is one lane, in this order:
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
  Open: the silence window comes from measured runs; its value is not chosen.

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

## Open topics, not yet discussed

- How many lanes start: the owner said in the same answer "the limit isn't the problem, it's how the
  limit batches that's the problem". Covered by stage 3.4 for now.
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
