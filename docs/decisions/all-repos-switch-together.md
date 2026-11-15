# Six repos are ordered to merge per lane now, q_max waits; any other repo switches together at the cutover

## The ruling

Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: the per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect together. No repo switches alone, except as the rulings below say.

Owner ruling `own-degen-home-switch-now` (degen and home switch now), 2026-11-13 22:13 CST, is an exception to this decision. Degen and home switch to per-lane merge on the stable branch ahead of the drain.

Owner ruling `own-820-c-five-repos` (per-lane merge for five more repos), page save 2026-11-14 00:19 CST, item 820, pick c, extends that exception. It says: "extend the 22:13 CST exception (ruling own-degen-home-switch-now) to all five repos now: q_max, banchi, mailaudit, ios-adblock and joyous." The batch runner merges a lane's own PR on its own green run in each. The grant covers those five repos and that act only. The coordinator (00:32 CST Nov 14, relayed, its own pick) says q_max runs CI only on a branch starting with `batch-`, so the act as named cannot happen there. Whether a one-lane `batch-<slug>` branch is covered is the owner's open question (item 821); the grant is not widened to it.

Both exceptions override ruling `own-act6-draft-prs-when-green` (child-repo draft PRs open once claude-settings main is green; the switch waits for the drain), for the seven named repos only.

State: per-lane merge on the stable branch is ordered now in degen, home, banchi, mailaudit, ios-adblock and joyous. What each repo's settings change is for the lane that builds it, so "live" holds only where a per-lane merge is recorded. In q_max the order stands, but the act as named is blocked until item 821 is answered. Target, not live, for every other repo: each waits for the drain and switches at the cutover. q_max keeps its batch path until item 821 is answered. The cutover lands with the removal act, act 4 of R42 part 2, which is a branch in progress.

- The merge tool is one shared script that every repo runs (`merge/merge.py`). A cutover in one repo gives that tool two rule sets. The exceptions accept that for the seven named repos.
- Decision `uniform-over-variants` forbids one rule set per repo. Q1 a applies it to the cutover. The two exceptions above are the only departures.
- Child repos read the stable branch (decision `stable-branch`) and fall back as decision `stable-fallback-warn` says. Both land before the cutover.
- Until the cutover, every repo the two rulings do not name keeps its batch path, and so does q_max until item 821 is answered. A red main keeps the brake of decision `no-merge-onto-red-main`.

Why: act 4 changes the shared merge tool. Child repos would lose batching and get no stable branch or revert route if the cutover came first in one repo. Refuter, 2026-11-11 22:58 CST, gap 3.

Kind: process
Home: docs/decisions/uniform-over-variants.md
