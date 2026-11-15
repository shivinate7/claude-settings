# Seven repos are granted per-lane merge now; other child repos switch together

## The ruling

Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: the per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect together. No repo switches alone, except as the next ruling says.

Owner ruling `own-degen-home-switch-now` (degen and home switch now), 2026-11-13 22:13 CST, is an exception to this decision. Degen and home switch to per-lane merge on the stable branch ahead of the drain. Child repos that no ruling here names wait for the drain, then switch together at the cutover.

Owner ruling `own-820-c-five-repos` (five repos named), waiting-page item 820 pick c, 2026-11-14 00:19 CST, extends the 2026-11-13 22:13 CST exception to q_max, banchi, mailaudit, ios-adblock and joyous. The grant covers these five repos and that act only, no other repo. It is granted now for all five. The batch runner merges a lane's own PR on its own green run in each. The ruling's linked step is `mutation-report-child-adoption`; what each repo's settings change is, is for the lane that builds it. The record sits on the roadmap branch, not main. In q_max the act as named (a lane's own PR on its own green run) cannot happen, by the coordinator's relay (00:32 CST Nov 14). It is a relay, not an owner ruling. CI in q_max runs only on a branch starting with `batch-`. q_max merges as a one-lane `batch-<slug>` branch per lane head under ruling `own-821-a` (owner 02:36 CST Nov 14, relayed 02:37 CST; q_max and that form only).

The exception overrides ruling `own-act6-draft-prs-when-green` (child-repo draft PRs open once claude-settings main is green; the switch waits for the drain), for the repos the exception covers (see State).

State: granted now for seven repos: degen and home (ruling 2026-11-13 22:13 CST, which grants per-lane merge on the stable branch), and q_max, banchi, mailaudit, ios-adblock and joyous (ruling 2026-11-14 00:19 CST). Degen and home: step `merge-flow-after-anthropic`. The other five: the ruling's linked step is `mutation-report-child-adoption`. What each repo's settings change is, is for the lane that builds it. Live state is unmeasured here. Each child repo that no ruling names waits for the cutover. The cutover lands with the removal act, act 4 of R42 part 2, which is a branch in progress.

- The merge tool is one shared script that every repo runs (`merge/merge.py`). A cutover in one repo gives that tool two rule sets. The exceptions accept that for each repo they grant.
- Decision `uniform-over-variants` forbids one rule set per repo. Q1 a applies it to the cutover. The exceptions above are the one departure.
- Child repos read the stable branch (decision `stable-branch`) and fall back as decision `stable-fallback-warn` says. Both land before the cutover.
- Until the cutover, every repo not granted now keeps its batch path, and a red main keeps the brake of decision `no-merge-onto-red-main`. q_max's one-lane form is under ruling `own-821-a`, not this path.

Why: act 4 changes the shared merge tool. Child repos would lose batching and get no stable branch or revert route if the cutover came first in one repo. Refuter, 2026-11-11 22:58 CST, gap 3.

Kind: process
Home: docs/decisions/uniform-over-variants.md
