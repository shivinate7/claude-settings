Done
- OTHER: degen CLAUDE.md audit (Explore, opus), read-only. It has 46 lines but 16,832 bytes (about 4,200 tokens) in 16 one-line rules. Four rules hold 10.7 KB: deploy check-in 3,588 B, tests once per batch 3,384 B, bulk pacing 2,000 B, sim lease 1,690 B. Target is about 27 lines and 3.7 KB (about 900 tokens).
- OTHER: classes, one primary class per rule:
  - KEEP: 7 rules, 11,766 B. Only about 3.1 KB of that survives a trim.
  - DUP: 7 rules, 2,618 B.
  - STALE: 1 rule, 465 B.
  - MOVE: 1 rule, 1,690 B.
  - PATH: 0 whole rules. Two clauses are PATH: the strip prefetch limits (native/DegenKit/Sources/DegenKit/Viewer/) and the action pins (.github/workflows/), if they stay.
- OTHER, wrong KEEP: `merge-grant` (who may merge, CLAUDE.md:7) lets the coordinator merge. That is stale. /home/user/claude-settings/docs/decisions/standing-merge-grant.md:7 (owner, 2026-11-01 21:34 CST) and session-tiers ruling fb-1541-1 (who runs `merge --role`) say the coordinator never merges; a batch runner merges under the coordinator's grant. Keep only the two one-fresh-read cases from waiting-page item 83. The rest restates parent rules (CI green, review, lone lane).
- OTHER, DUP, cut whole:
  - :8 `lanes-hand-off-to-batch-runner` (lanes hand drafts to the batch runner). Restates git-integration-branch-merge (batch merging) and the session-tiers refusal that hands the PR to the batch runner.
  - :12 `own-worktree-always` (work in own worktree). Restates shared-trees-one-checkout-per-agent. Its "none enforces it yet" is stale: guard rule session-home (blocks writes when the worktree is gone) enforces it, at guard.py:3866-3875.
  - :13 `session-cleanup-archive` (clean up, archive). Restates shared-trees-no-machine-wide-kill (kill only yours), decision machine-load-brake (load limit), and the session-tiers batch-runner duty to archive lanes.
  - :19 `prose-is-ste` (write Markdown in STE). Restates output-write-in-ste (write plainly).
  - :27 `records-slug-then-stamp` (slug now, number at merge). Restates git-slug-then-claim-number.
  - :31 `actions-pinned` (pin actions by SHA). Restates the ci-hygiene skill, step 7, at skills/ci-hygiene/SKILL.md:47-49.
  - :40 `tests-pin-rulings` (one red test per ruling). Restates roles-each-layer-proves-once (red tests first) and roles-brief-contents (rulings in the brief).
- OTHER, STALE: :23 `owner-question-pictures` (pictures in option cards). Its fallback ("until the page can place a picture in each card") is out of date: the waiting page now puts a picture at the top of each option card (skills/waiting-page/SKILL.md:71-74). The rest restates that skill.
- OTHER, biggest cuts, all MOVE:
  - :35 deploy check-in. Keep:
    - the check-in, under 5 minutes old
    - `tools/deploy-degen <full sha>` as the only deploy path
    - green-health before a manual restart or bulk import
    - one deploy per batch
    - no deploy while a hold is open

    Move the six gate thresholds, the knobs, the lock order and the test case numbers 74-84 to tools/deploy-degen (39 refusal lines) and tools/deploy-degen_test.sh:771-798. Move the crash story to the home repo's freeze record.
  - :39 tests once per batch. Keep the lane test scope, one `make native-check` per batch, and the `milestone-proof` job. The record line format is already at scripts/native_run_check.py:10,38. Move the check mechanics to the docstrings of that file and of scripts/native_ci_check.py.
  - :46 bulk pacing. Keep the pace, the slices, no bulk job during a build, deploy or sync, and "backups are paused". Move the crash history. The check detail is already at scripts/bulk_pace_check.py:9-39.
  - :41 one Xcode build at a time. Cut the load readings and the history of the dropped CPU and memory checks. That text is superseded (speak-rewrite-superseded-in-place).
  - :42 sim lease:
    - The UDIDs and the owner quotes are MOVE: `simctl list` and README.md:94 already give the UDIDs.
    - The cap of two booted simulators restates guard rule simulator-boot-cap (`SIM_BOOT_CAP = 2`, guard.py:3563).
    - "The gatekeeper's sim-lease tool will enforce it" is STALE: no such tool exists in claude-settings.
    - Keep the load limits (boot only under 100, second slot only under 60). Nothing checks them; README.md:94 says so.
- OTHER, MISSING:
  - CLAUDE.md never names `sim-test` as the one boot path (decision sim-test-is-the-one-boot-path); only README.md:94 does.
  - "Mac sim gatekeeper" (:41, :42) uses `gatekeeper`, which GLOSSARY.md:51 lists bare as a retired name. That breaks speak-one-name-per-thing (one name per thing).
  - README.md:7 says "Skeleton only", which is stale.
  - Degen has no docs/map/, so tokens-read-map-first (read the map first) finds nothing to read.
- OTHER, mechanical check: yes, one could have caught it. check_claude_md_size.py counts newlines, so it prints ok at 46 lines. ste-lint caps words per sentence (ste_lint.py:386), not words per bullet. A byte cap or a per-bullet cap (about 600 B) would flag :7, :35, :39, :41, :42 and :46. Degen's Makefile does not run the size check at all.

Deviations
- I read claude-settings at detached HEAD 88266e82 (2026-11-03) and did not check it against origin/main. Unknown: whether a Mac sim gatekeeper session still exists, and whether "automatic backups are paused" (:46) is still true.

Next
- A degen lane: fix `merge-grant` first, then cut to the KEEP kernel. A claude-settings lane: add a byte cap to check_claude_md_size.py.