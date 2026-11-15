# Named repos switch to per-lane merge now; other child repos switch together

## The ruling

Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: the per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect together. No repo switches alone, except as the next ruling says.

Owner ruling `own-degen-home-switch-now` (degen and home switch now), 2026-11-13 22:13 CST, is an exception to this decision. Degen and home switch to per-lane merge on the stable branch ahead of the drain. Child repos not named in an exception wait for the drain, then switch together at the cutover.

Owner ruling `own-820-c-five-repos` (five repos switch now), waiting-page item 820 pick c, 2026-11-14 00:19 CST, extends the 2026-11-13 22:13 CST exception to q_max, banchi, mailaudit, ios-adblock and joyous, now. The batch runner merges a lane's own PR on its own green run in each. The grant covers those five repos and that act only, no other repo. Its record sits on the roadmap branch, not main. Caveat: the coordinator relayed at 2026-11-14 00:32 CST, not the owner's word, that CI in q_max runs only on a branch starting with `batch-`. So the act as named cannot happen there. Owner item 821 (whether a one-lane `batch-<slug>` branch is covered) is unanswered. q_max is named by the ruling; whether it is live is an Owner call.

The exception overrides ruling `own-act6-draft-prs-when-green` (child-repo draft PRs open once claude-settings main is green; the switch waits for the drain), for the repos the exception covers (see State).

State: live for degen and home (ruling 2026-11-13 22:13 CST, which switches them to per-lane merge on the stable branch), and for banchi, mailaudit, ios-adblock and joyous (ruling 2026-11-14 00:19 CST, which extends that exception to them). q_max is named by its ruling, but its live state is an Owner call (item 821). No other child repo has switched. Each waits for the cutover. The cutover lands with the removal act, act 4 of R42 part 2, which is a branch in progress.

- The merge tool is one shared script that every repo runs (`merge/merge.py`). A cutover in one repo gives that tool two rule sets. The exceptions accept that for each repo they cover.
- Decision `uniform-over-variants` forbids one rule set per repo. Q1 a applies it to the cutover. The exceptions above are the one departure.
- Child repos read the stable branch (decision `stable-branch`) and fall back as decision `stable-fallback-warn` says. Both land before the cutover.
- Until the cutover, every repo not covered by an exception keeps its batch path, and a red main keeps the brake of decision `no-merge-onto-red-main`. q_max's path waits on item 821.

Why: act 4 changes the shared merge tool. Child repos would lose batching and get no stable branch or revert route if the cutover came first in one repo. Refuter, 2026-11-11 22:58 CST, gap 3.

Kind: process
Home: docs/decisions/uniform-over-variants.md
