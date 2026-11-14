# Plan: child repo gap (step child-repo-gap, part 1)

Goal (owner, 2026-11-11 14:05 CST, R44: "on r44 yea agreed A build all 3"): each child repo follows
claude-settings main, with cited exceptions only. This record is part 1, the measure, and the list of fix lanes it feeds. The other R44 builds (stable-branch action
pins, a child-CI check for contradicting lines, the one-time sweep) are separate builds. The repo lanes below, and the two lists for the owner, are that sweep.

Measured on 2026-11-12 from shallow clones, git and file reads only, against claude-settings main at
36807ad19. Heads read: q_max 32d4373, home 85fbf7e, joyous f510db0, banchi 70c6bc6, degen 959bf79,
mailaudit b56997a, ios-adblock f0ace6e. One Explore agent read each repo (audit, sonnet).

Refuter: refuter opus, 2026-11-12, revise (all eight points answered in this revision: recount, stable branch status, arbiter dropped, protection prose moved to the ruleset sweep, the lanes are the one-time sweep, run through skill compliance-check, order measure stated, grant question named as unknown)

## Read this first

- **Unmeasured everywhere:** the live branch protection or ruleset of every repo. Files only describe
  it. No API read ran. Nothing here claims a live state.
- **Commit counts in the per-repo tables are superseded.** The agents counted in shallow clones, so their numbers differ.
  The refuter recounted in the full claude-settings checkout (not shallow) with `git rev-list --count <pin>..origin/main`:
  all commits, not only changes under the action folders. Main moves, so these rise by the hour (count at 21:20 CST
  Nov 12). Pins by repo: q_max 2ac382cc6 3298. banchi 919106e7 5020. ios-adblock da8d8073 6267. mailaudit 380a24b 4839,
  ste-lint e0b9696 2965, ios-ship eaaf66e 3293. joyous 59bff08 5305, a781a86 5004, d70ebd1 4349, 2deb827 228. degen
  635b37b 5736, 422cbbd 3791, ios-ship ddaa393 2013. home all-jobs-passed 7b49661 5996, ste-lint 8bc2898 2392, lint raw URL
  1cc47f0 8621. ios-adblock mutation-report a48189d0 4983, ci-alarm 59bff081 5305. A pin that is not an ancestor of main inflates its count; ancestry was not checked.
- **Main today, not ruled.** Main's ruleset (main-branch-protection ruling r) is ruled but not built, and main still runs CI
  on push to main (checks.yml:4-5). R61-R63 (once per batch) are rulings on the roadmap branch, not yet built. The Gold column
  names the ruled form.
- **CI once-per-batch items are marked "R64: when runners are free."** R64 (owner 16:01 CST Nov 12)
  holds child-ci-once-per-batch until the runners have free time.
- All seven repos have the `all-jobs-passed` check (each repo's CI form row below). No repo is missing it.
- All seven repos pin claude-settings actions by commit, not by a stable branch (R44 part 1). None of
  the seven runs the child-CI check for contradicting lines (R44 part 2). Only home and joyous run
  `claude-md-cites`, both pinned at 2deb827; joyous's count is above, home's is not separately measured.

## Cross-repo table

| Area | Gold (main) | q_max | home | joyous | banchi | degen | mailaudit | ios-adblock |
|---|---|---|---|---|---|---|---|---|
| Action pin age | Stable branch | 9 pins at 2ac382cc6 (Nov 8), far behind (counts above) | Mixed (counts above) | Mixed (counts above) | 8 pins at 919106e7, behind (counts above) | 4 to 8 days behind by date | Mixed (counts above) | Mixed (counts above) |
| `claude-md-cites` in CI | Yes | No | Yes | Yes (counts above) | No | No | No | No |
| project-ops roles | Roster, record branch, briefs, handoffs | Roadmap branch scaffold, no steps, no roster | Roadmap branch, roster on claude.ai | None | Roadmap branch, contents unread | Roadmap branch, contents unread | Roadmap branch, roster on claude.ai | None |
| Push to main re-runs CI | No (ruled in R61-R63, not built) | Yes (R64: when runners are free) | Yes except ios job (R64: when runners are free) | Yes (R64: when runners are free) | Yes (R64: when runners are free) | Yes (R64: when runners are free) | Yes (R64: when runners are free) | Yes (R64: when runners are free) |
| Protection form in files | Ruleset (ruled, not built) | Claims gold form, unmeasured | stamp.json only, unmeasured | stamp.json only, unmeasured | Old form in prose, unmeasured | Unknown: only a plan line (docs/specs/plan.md:2549) | Old form in prose, unmeasured | Old form in CLAUDE.md line 6, unmeasured |

## Per-repo gap tables

### q_max

| Area | Main has | q_max has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records, copies none | 180 lines, cites by name, no verbatim copy found. 14 of 16 ids exist as rules, the other two are decision slugs that exist. The `restates` probe was not run. | Small. A copy would pass unseen because CI never calls `claude-md-cites`. |
| Contradiction with no exemption | A child contradicts a parent line only by citing it, with the owner's grant | D-705 (CLAUDE.md:55) lets the batch runner merge over a failing `browser.yml` run on main (owner 2026-11-07 13:13 CST). It does not name the parent rule `git-never-merge-failing-ci`. D-705:19 uses a role, "primary orchestrator", that session-tiers does not define. D-499 and D-833 (CLAUDE.md:17-19) lock the lint to a pinned commit with no R44 exemption. | One exemption line, one role rename, one exemption or retirement for the pinned-lint lock. |
| project-ops | Roster, record branch, briefs, handoffs | A `roadmap` branch (3804a024b) with empty data folders, briefs, handoffs, an outbox and its own CLAUDE.md. `tiers.yml` is a probes workflow. | Scaffold only: no steps recorded, no roster found. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:670 and browser.yml:181. 9 pins at 2ac382cc6 (Nov 8), behind (counts above). | All 9 pins move to a stable branch. |
| Once per batch | PR only for the batch (R61-R63, not built) | PR trigger only for `claude/int-batch-*` (checks.yml:14, :123), but push to main still runs checks (:85-86). Browser checks run on dispatch only. | R64: when runners are free. |
| Shared hooks, skills, lint | Come from claude-settings | No copies. ste-lint and the map skill come through the pin. Three q_max-only hooks. | None beyond the pin. Moving the pin fixes it. |

### home

| Area | Main has | home has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 57 lines, zero `rule:` anchors, no stale ids, no contradiction found. Lines 29 and 31 restate the batch-runner and coordinator split. | Possible copy, unconfirmed. |
| project-ops | Roster, record branch, briefs, handoffs | Roles named (CLAUDE.md:27-29). `origin/roadmap` exists (61687fe). The roster is on claude.ai, not in the repo. | Roster, briefs and handoffs unmeasured.  |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:170-176. All refs are commit pins. all-jobs-passed at 7b49661 is 1 behind by folder, mutation-report at a781a86 is 4 behind, ste-lint (8bc2898) and claude-md-cites (2deb827) are closer to main than the other pins; their counts are above. The shared-resources lint comes from a raw URL at 1cc47f0 (checks.yml:68-71), behind (counts above) on `lint/`. testflight.yml:135 fetches `bin/ios-ship` at eaaf66e, age unmeasured. | Pins are not a branch. Raw URL stale (behind (counts above) on `lint/`); ios-ship age unmeasured. |
| Once per batch | PR only for the batch (R61-R63, not built) | Push to main skips only the ios job (decision ci-push-skips-macos). Push, nightly and PR synchronize still run the rest. | R64: when runners are free. |
| Hooks and skills | Come from claude-settings | Only its own tailscale and green-ssh hooks. | None found. |

### joyous

| Area | Main has | joyous has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 51 lines, repo-only rules with their own ids, cites `standing-merge-grant`. No copies, no stale ids, no contradiction. | Small: lines 21-24 point at paths, not record ids. |
| project-ops | Roster, record branch, briefs, handoffs | Nothing found. No roadmap branch. | Absent. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:21-29. Pins: 59bff08 (five actions) behind (counts above), a781a86, d70ebd1, 2deb827 (counts above). | Pin lines to move: four distinct commits in checks.yml and one in links.yml. |
| Once per batch | PR only for the batch (R61-R63, not built) | checks.yml:2-8 runs on PR, push to main and dispatch. | R64: when runners are free. |
| Shared parts | Come from claude-settings | No hooks or lint. Skills are vendored third-party only. | A record naming the shared pieces it uses is missing. |

### banchi

| Area | Main has | banchi has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 169 lines, cites existing records, no `rule:` ids, none stale. By reading, not by the probe: probable copies of the decision-is-an-argument rule (~line 88), the main-by-pull-request block, the screen-before-verdict rule, one-home-per-capability and the stash rule. | Copies to cut to cites. |
| Contradiction with no exemption | Cited exception with grant | A "never --admin" line and D42 (`enforce_admins` true) match the classic protection main runs today, per the record. They are no contradiction now, and go into the ruleset sweep. | Rewrite to the ruleset form in the sweep. |
| project-ops | Roster, record branch, briefs, handoffs | `origin/roadmap` (bb560f6), `records/*` and `seed/banchi-roadmap` exist. Contents unread. No roster or handoff file in the tree. | Contents unmeasured. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:362-368. Eight actions at 919106e7 (Nov 5), behind (counts above). Not used: claude-md-cites, ste-lint, silent-undo, ruling-kind. Zizmor is a local job. | Pins and four missing actions. |
| Once per batch | PR only for the batch (R61-R63, not built) | Draft pull requests skip, mutation-report is batch-only, but push to main and a nightly run still run the full suite. | R64: when runners are free. |
| Guards | Shared guards | Own guard-shell, guard-opsec, githooks and decision-context scripts. Overlap with shared guards unmeasured. | Unmeasured. |

### degen

| Area | Main has | degen has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records, short rules | The `restates` probe says in shape (5 files read). Lines 7, 35 and 39 are single paragraphs of 1,000 to 3,000 characters. 8 shared rule ids cited, none stale. | Three paragraphs break `speak-never-explain-in-paragraph`. The probe misses paraphrase. |
| Exception | Names the parent rule and the grant | Line 7 (fresh reviewer per lane, owner 2026-11-03 14:56 CST, D10) names `git-integration-branch-merge`, not `roles-solo-reviews-logic-diffs-only`. Line 35 (deploy at any time, owner 2026-11-06 16:32 CST) was not tested against the root rule. | Parent rule name missing on line 7. |
| project-ops | Roster, record branch, briefs, handoffs | Roles named (lines 8, 12, 13). `roadmap` branch (93320ca) and `archive/handoff/*` exist. No roster, brief or handoff file in the tree. | Contents unmeasured. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:444 needs `native-record`. The `ci-done` list (:457) omits `native-record`. Pins: 635b37b (Nov 4), 59bff08 (Nov 5), 422cbbd (Nov 8), `IOS_SHIP_SHA` ddaa393. The lint scripts come from a raw URL at 635b37b. Not used: claude-md-cites, ruling-kind, silent-undo, zizmor action. | Pins 4 to 8 days behind, no branch. `ci-done` misses a job. |
| Once per batch | PR only for the batch (R61-R63, not built) | checks.yml:3-10 runs on PR, push to main, nightly and dispatch. | R64: when runners are free. |
| Protection | Ruleset (ruled, not built) | Item 78 stays unknown. Only a plan line (docs/specs/plan.md:2549) says a lane sets protection. No file reads it back. | Unmeasured. |

### mailaudit

| Area | Main has | mailaudit has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 94-line slug index, no `rule:` markers, no copies. AGENTS.md is also 94 lines and carries the same head (diff not run). One mislabel: `guard-guards-mistakes-only` is cited as a rule at docs/decisions/milestone-runs-full-suite.md:67, but it is a decision. | Duplicate file is a drift risk. One mislabel. |
| project-ops | Roster, record branch, briefs, handoffs | Adopted by record (session-tiers-adopted.md:3, 2026-10-28 02:31 CDT). `roadmap` branch (40d07f9). The roster is in claude.ai project instructions, not the repo. | Briefs and handoffs unmeasured. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:351, `ci-done` at :364. Pins: 380a24b (five uses) behind (counts above), ste-lint e0b9696 behind (counts above), ios-ship raw URL eaaf66e (testflight.yml:71) behind (counts above). Not used: claude-md-cites, code-check, silent-undo, ruling-kind, stamp, readme-links, playwright-setup. Zizmor is a local job. | Pins and missing actions. |
| Once per batch | PR only for the batch (R61-R63, not built) | checks.yml:14-16 still runs on push to main, plus a nightly (:46). | R64: when runners are free. |
| Protection | Ruleset (ruled, not built) | Records describe the old `enforce_admins` form (main-moves-only-by-pr.md:3,5; orchestrator-may-merge.md). | Records need a rewrite once the ruleset is confirmed. |

### ios-adblock

| Area | Main has | ios-adblock has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 8 lines. AGENTS.md is a symlink to CLAUDE.md (mode 120000; coordinator, 21:43 CST), so it is no duplicate. Cites `standing-merge-grant`. Line 6 says protection enforces `all-jobs-passed` for admins too (owner 2026-10-10). | Line 6 restates a protection fact. It matches the classic protection main runs today, per the record (enforce_admins true; no live setting was read), so it is no contradiction now. It goes into the ruleset sweep. |
| project-ops | Roster, record branch, briefs, handoffs | None. 49 heads, no roadmap branch. | Absent. |
| CI form | One `all-jobs-passed` check; stable-branch actions (R44, not built) | `all-jobs-passed` at checks.yml:204. Pins: da8d8073 (checks.yml:108, :173, :204; doc-links.yml:17) behind (counts above), mutation-report a48189d0 (:195) behind (counts above), ci-alarm 59bff081 (:213) behind (counts above). Sparse pin of `bin/verdict` and `hooks/_nowindow.py` at da8d8073. Not wired: claude-md-cites, ste-lint, silent-undo, ruling-kind, ci-done-comment. | Pins, and five unused shared actions. |
| Once per batch | PR only for the batch (R61-R63, not built) | checks.yml:4-6 runs on PR and push to main, nightly at :9. | R64: when runners are free. |

## Scope of the lanes (coordinator, 21:14 CST Nov 12, relaying the owner at 21:12 CST)

The owner is already working in degen and home. The coordinator starts fix lanes for the other five repos (joyous,
ios-adblock, mailaudit, banchi, q_max). For degen and home, the lists below are what each needs to get on board, and the
coordinator passes them to the owner. No lane starts in either repo. The lanes are the R44 one-time sweep, so each runs
through skill compliance-check (R44 item 2, restart-plan.md:731-733), so there is no separate sweep list. The plan that decision action-pins-follow-sessions clause (c) waits on (step c76) was given by the owner on Oct 28 at 02:31 CDT (waiting-page item 2 a: "yes to the one plan; the other-repo part lands through PRs in each repo"). R44 point 1 (owner 14:05 CST Nov 11) moves child CI to the stable branch for all child repos (triage, 21:49 CST Nov 12). So pin moves start once lane-stable-mover lands. The clause (c) text in that decision is stale and is not edited here.

## What waits on the stable branch

No stable branch for child CI exists on origin today. Branch `lane-stable-mover` (tip dc5021cc6, Nov 12) is the lane
building it, unmerged, with three open gaps in its own notes. Every pin move below waits on it. The acts that can start now
are the ones that are not pin moves.

## What feeds the shared R44 builds

- **Stable branch for child CI (R44 pins):** every repo. Pins are named per repo above. This build reaches all seven at once.
- **Contradiction check in child CI (R44 contradiction check):** the cases it must catch, found by reading: q_max D-705 and
  D-499/D-833 (no parent rule named), degen line 7 (names a different parent rule than the one it departs from),
  mailaudit's mislabeled rule id. The cases that are no contradiction today: ios-adblock CLAUDE.md line 6 and banchi's
  "never --admin" and `enforce_admins` wording, which match the classic protection main runs now, per the record. The check must not flag
  them until the ruleset is built. Joyous and home show none. A test that no `@<sha>` pin remains belongs to this build.

## Fix lanes

Ordered by the count of acts that can start now (not pin moves, not R64 items), fewest first; a tie keeps the order shown.
Each lane lands in its own repo through that repo's batch runner. Every lane also moves its pins when the stable branch lands.

1. **ios-adblock** (1 act now). Add project-ops. Then, once the stable branch lands: add `claude-md-cites`, `ste-lint` and `silent-undo` under `all-jobs-passed` (none exists at the child's pin da8d8073, so wiring them waits on the stable branch, coordinator 21:43 CST). R64: when runners are free: once-per-batch trim.
2. **joyous** (2 acts). Add a record naming the shared pieces joyous uses. Add project-ops (roster, roadmap branch). R64: when runners are free: drop the push-to-main re-run.
3. **mailaudit** (3 acts). Add `claude-md-cites`, `code-check`, `ruling-kind` and `silent-undo`. Fix the mislabel. Cut AGENTS.md to a pointer. R64: when runners are free: drop the push-to-main trigger.
4. **banchi** (3 acts). Add `claude-md-cites` and `ste-lint`. Cut the restated rules in CLAUDE.md to cites. Read the roadmap branch and add roster and handoff pointers. R64: when runners are free: once-per-batch trim.
5. **q_max** (4 acts). Rewrite D-705 to name `git-never-merge-failing-ci` and replace "primary orchestrator". Add an R44 exemption for D-499 and D-833, or retire them after the pins move. Add `claude-md-cites`. Fill the roadmap data and roster. R64: when runners are free: drop the push-to-main re-run.
5. **q_max** (4 acts). Rewrite D-705 to name `git-never-merge-failing-ci` and replace "primary orchestrator". Add an R44 exemption for D-499 and D-833, or retire them after the pins move. Add `claude-md-cites`. Fill the roadmap data and roster. R64: when runners are free: drop the push-to-main re-run.

For the owner (degen and home, no lane started):

- **home** (2 acts). Cite instead of restate CLAUDE.md lines 29 and 31, after reading project-ops. Point CLAUDE.md at the roster on claude.ai. Pins: all-jobs-passed, mutation-report, the raw-URL lint and `bin/ios-ship`. R64: when runners are free: once-per-batch trim.
- **degen** (4 acts). Add `claude-md-cites` under `all-jobs-passed`. Add `native-record` to the `ci-done` list. Name the parent rule on line 7. Split lines 7, 35 and 39. Pins as listed above. R64: when runners are free: drop the push-to-main trigger.

## Source items not carried into a lane

- **Ruleset reads and the move to the ruleset form** (all seven repos, degen's item 78 among them): no API read ran in this audit. One read lane on a session on the owner's computer reads the seven rulesets together. The protection prose in
  ios-adblock line 6, banchi D42 and mailaudit's records is rewritten in the ruleset sweep, not in a repo lane here.
- **degen roadmap compare** is folded into its project-ops step, once a lane can fetch `origin/roadmap`.
- **Arbiter:** an arbiter starts only when the owner says so (session-tiers), so its absence is no gap. No lane adds one.
- **Unused shared actions** the agents listed that no lane above names (`ruling-kind` and `ci-done-comment` for
  ios-adblock, `zizmor` for banchi, mailaudit and degen, `silent-undo` and `ruling-kind` for degen and banchi, `stamp`, `readme-links` and `playwright-setup` for mailaudit): each
  lane decides when it starts whether the repo needs the action. None is dropped as unwanted here.
