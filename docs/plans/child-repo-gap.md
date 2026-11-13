# Plan: child repo gap (step child-repo-gap, part 1)

Goal (owner, 2026-11-11 14:05 CST, R44: "on r44 yea agreed A build all 3"): each child repo follows
claude-settings main, with cited exceptions only. This record is part 1, the measure, and the list of fix lanes it feeds. The other R44 builds (stable-branch action
pins, a child-CI check for contradicting lines, the one-time sweep) are separate lanes.

Measured on 2026-11-12 from shallow clones, git and file reads only, against claude-settings main at
36807ad19. Heads read: q_max 32d4373, home 85fbf7e, joyous f510db0, banchi 70c6bc6, degen 959bf79,
mailaudit b56997a, ios-adblock f0ace6e. One Explore agent read each repo (audit, sonnet).

## Read this first

- **Unmeasured everywhere:** the live branch protection or ruleset of every repo. Files only describe
  it. No API read ran. Nothing here claims a live state.
- **Commit counts are unreliable.** The clones are shallow and the local `main` ref in the
  claude-settings checkout was stale for some agents. q_max's pin shows 2124 commits behind here and 2758 in the R44 scan of
  Nov 11 (restart-plan R44), so the counts disagree. Read them as "far behind". Dates and folder-scoped counts are given
  where an agent used them.
- **Main today, not ruled.** Main's ruleset (main-branch-protection ruling r) is ruled but not built, and main still runs CI
  on push to main (checks.yml:4-5). R61-R63 (once per batch) are rulings on the roadmap branch, not yet built. The Gold column
  names the ruled form.
- **CI once-per-batch items are marked "R64: when runners are free."** R64 (owner 16:01 CST Nov 12)
  holds child-ci-once-per-batch until the runners have free time.
- All seven repos have the `all-jobs-passed` check (each repo's CI form row below). No repo is missing it.
- All seven repos pin claude-settings actions by commit, not by a stable branch (R44 part 1). None of
  the seven runs the child-CI check for contradicting lines (R44 part 2). Only home and joyous run
  `claude-md-cites`, both pinned at 2deb827 (home: 0 commits behind on its folder; joyous: 217 behind).

## Cross-repo table

| Area | Gold (main) | q_max | home | joyous | banchi | degen | mailaudit | ios-adblock |
|---|---|---|---|---|---|---|---|---|
| Action pin age | Stable branch | 9 pins at 2ac382cc6 (Nov 8), far behind (2124 and 2758 both reported) | Mixed: 0 to 410 behind by folder | 217 to 2650 behind | 8 pins at 919106e7, 2652 behind | 4 to 8 days behind by date | 2029 to 2578 behind | 262 to 272 behind |
| `claude-md-cites` in CI | Yes | No | Yes | Yes, 217 behind | No | No | No | No |
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
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:670 and browser.yml:181. 9 pins at 2ac382cc6 (Nov 8), 36 first-parent merges and 2124 commits behind. 7 commits since touch the pinned action folders. | All 9 pins move to a stable branch. |
| Once per batch | PR only for the batch, no push re-run | PR trigger only for `claude/int-batch-*` (checks.yml:14, :123), but push to main still runs checks (:85-86). Browser checks run on dispatch only. | R64: when runners are free. |
| Shared hooks, skills, lint | Come from claude-settings | No copies. ste-lint and the map skill come through the pin. Three q_max-only hooks. | None beyond the pin. Moving the pin fixes it. |

### home

| Area | Main has | home has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 57 lines, zero `rule:` anchors, no stale ids, no contradiction found. Lines 29 and 31 restate the batch-runner and coordinator split. | Possible copy, unconfirmed. |
| project-ops | Roster, record branch, briefs, handoffs | Roles named (CLAUDE.md:27-29). `origin/roadmap` exists (61687fe). The roster is on claude.ai, not in the repo. No arbiter named. | Roster, briefs and handoffs unmeasured. Arbiter missing. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:170-176. All refs are commit pins. all-jobs-passed at 7b49661 is 1 behind by folder, mutation-report at a781a86 is 4 behind, ste-lint and claude-md-cites are current. The shared-resources lint comes from a raw URL at 1cc47f0 (checks.yml:68-71), 410 commits behind on `lint/`. testflight.yml:135 fetches `bin/ios-ship` at eaaf66e, age unmeasured. | Pins are not a branch. Raw URL stale (410 behind on `lint/`); ios-ship age unmeasured. |
| Once per batch | PR only for the batch | Push to main skips only the ios job (decision ci-push-skips-macos). Push, nightly and PR synchronize still run the rest. | R64: when runners are free. |
| Hooks and skills | Come from claude-settings | Only its own tailscale and green-ssh hooks. | None found. |

### joyous

| Area | Main has | joyous has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 51 lines, repo-only rules with their own ids, cites `standing-merge-grant`. No copies, no stale ids, no contradiction. | Small: lines 21-24 point at paths, not record ids. |
| project-ops | Roster, record branch, briefs, handoffs | Nothing found. No roadmap branch. | Absent. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:21-29. Pins: 59bff08 (five actions) 2642 behind, a781a86 2650, d70ebd1 2301, 2deb827 217. | Pin lines to move: four distinct commits in checks.yml and one in links.yml. |
| Once per batch | PR only for the batch | checks.yml:2-8 runs on PR, push to main and dispatch. | R64: when runners are free. |
| Shared parts | Come from claude-settings | No hooks or lint. Skills are vendored third-party only. | A record naming the shared pieces it uses is missing. |

### banchi

| Area | Main has | banchi has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 169 lines, cites existing records, no `rule:` ids, none stale. By reading, not by the probe: probable copies of the decision-is-an-argument rule (~line 88), the main-by-pull-request block, the screen-before-verdict rule, one-home-per-capability and the stash rule. | Copies to cut to cites. |
| Contradiction with no exemption | Cited exception with grant | A "never --admin" line and D42 (`enforce_admins` true) differ from main's rule that the admin may bypass on pull requests. No exemption line. Live state unmeasured. | One exemption line, or a rewrite to the ruleset form. |
| project-ops | Roster, record branch, briefs, handoffs | `origin/roadmap` (bb560f6), `records/*` and `seed/banchi-roadmap` exist. Contents unread. No roster or handoff file in the tree. | Contents unmeasured. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:362-368. Eight actions at 919106e7 (Nov 5), 2652 commits behind. Not used: claude-md-cites, ste-lint, silent-undo, ruling-kind. Zizmor is a local job. | Pins and four missing actions. |
| Once per batch | PR only for the batch | Draft pull requests skip, mutation-report is batch-only, but push to main and a nightly run still run the full suite. | R64: when runners are free. |
| Guards | Shared guards | Own guard-shell, guard-opsec, githooks and decision-context scripts. Overlap with shared guards unmeasured. | Unmeasured. |

### degen

| Area | Main has | degen has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records, short rules | The `restates` probe says in shape (5 files read). Lines 7, 35 and 39 are single paragraphs of 1,000 to 3,000 characters. 8 shared rule ids cited, none stale. | Three paragraphs break `speak-never-explain-in-paragraph`. The probe misses paraphrase. |
| Exception | Names the parent rule and the grant | Line 7 (fresh reviewer per lane, owner 2026-11-03 14:56 CST, D10) names `git-integration-branch-merge`, not `roles-solo-reviews-logic-diffs-only`. Line 35 (deploy at any time, owner 2026-11-06 16:32 CST) was not tested against the root rule. | Parent rule name missing on line 7. |
| project-ops | Roster, record branch, briefs, handoffs | Roles named (lines 8, 12, 13). `roadmap` branch (93320ca) and `archive/handoff/*` exist. No roster, brief or handoff file in the tree. | Contents unmeasured. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:444 needs `native-record`. The `ci-done` list (:457) omits `native-record`. Pins: 635b37b (Nov 4), 59bff08 (Nov 5), 422cbbd (Nov 8), `IOS_SHIP_SHA` ddaa393. The lint scripts come from a raw URL at 635b37b. Not used: claude-md-cites, ruling-kind, silent-undo, zizmor action. | Pins 4 to 8 days behind, no branch. `ci-done` misses a job. |
| Once per batch | PR only for the batch | checks.yml:3-10 runs on PR, push to main, nightly and dispatch. | R64: when runners are free. |
| Protection | Ruleset (ruled, not built) | Item 78 stays unknown. Only a plan line (docs/specs/plan.md:2549) says a lane sets protection by `gh api`. No file reads it back. | Unmeasured. |

### mailaudit

| Area | Main has | mailaudit has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 94-line slug index, no `rule:` markers, no copies. AGENTS.md is also 94 lines and carries the same head (diff not run). One mislabel: `guard-guards-mistakes-only` is cited as a rule at docs/decisions/milestone-runs-full-suite.md:67, but it is a decision. | Duplicate file is a drift risk. One mislabel. |
| project-ops | Roster, record branch, briefs, handoffs | Adopted by record (session-tiers-adopted.md:3, 2026-10-28 02:31 CDT). `roadmap` branch (40d07f9). The roster is in claude.ai project instructions, not the repo. No arbiter. | Briefs and handoffs unmeasured. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:351, `ci-done` at :364. Pins: 380a24b (five uses) 2578 behind, ste-lint e0b9696 2029 behind, ios-ship raw URL eaaf66e (testflight.yml:71) 2119 behind. Not used: claude-md-cites, code-check, silent-undo, ruling-kind, stamp, readme-links, playwright-setup. Zizmor is a local job. | Pins and missing actions. |
| Once per batch | PR only for the batch | checks.yml:14-16 still runs on push to main, plus a nightly (:46). | R64: when runners are free. |
| Protection | Ruleset (ruled, not built) | Records describe the old `enforce_admins` form (main-moves-only-by-pr.md:3,5; orchestrator-may-merge.md). | Records need a rewrite once the ruleset is confirmed. |

### ios-adblock

| Area | Main has | ios-adblock has | Gap |
|---|---|---|---|
| CLAUDE.md | Cites records | 8 lines. AGENTS.md is an identical copy. Cites `standing-merge-grant`. Line 6 says protection enforces `all-jobs-passed` for admins too (owner 2026-10-10). | Line 6 restates a protection fact and contradicts main's admin bypass on pull requests, with no exemption. |
| project-ops | Roster, record branch, briefs, handoffs | None. 49 heads, no roadmap branch. | Absent. |
| CI form | One `all-jobs-passed` check, stable-branch actions | `all-jobs-passed` at checks.yml:204. Pins: da8d8073 (checks.yml:108, :173, :204; doc-links.yml:17) 272 behind, mutation-report a48189d0 (:195) 262 behind, ci-alarm 59bff081 (:213) 272 behind. Sparse pin of `bin/verdict` and `hooks/_nowindow.py` at da8d8073. Not wired: claude-md-cites, ste-lint, silent-undo, ruling-kind, ci-done-comment. | Pins, and five unused shared actions. |
| Once per batch | PR only for the batch | checks.yml:4-6 runs on PR and push to main, nightly at :9. | R64: when runners are free. |

## Fix lanes, smallest first

One lane per repo. The coordinator starts them. Each lane lands in its own repo through that repo's batch runner.

1. **joyous.** Move the claude-settings pins to a stable branch. Add a record naming the shared pieces joyous uses. Add project-ops (roster, roadmap branch). R64: when runners are free: drop the push-to-main re-run.
2. **ios-adblock.** Move the pins. Rewrite CLAUDE.md line 6 to cite `main-branch-protection`. Add `claude-md-cites`, `ste-lint` and `silent-undo` under `all-jobs-passed`. Add project-ops. Collapse AGENTS.md to a pointer. R64: when runners are free: once-per-batch trim.
3. **home.** Move the action pins and the raw-URL lint and `bin/ios-ship` refs to one stable branch. Cite instead of restate CLAUDE.md lines 29 and 31. Add an arbiter and roster pointer. R64: when runners are free: once-per-batch trim.
4. **mailaudit.** Move the pins and the ios-ship URL. Add `claude-md-cites`, `code-check`, `ruling-kind` and `silent-undo`. Fix the mislabel. Cut AGENTS.md to a pointer. Rewrite the protection records once the ruleset is confirmed. R64: when runners are free: drop the push-to-main trigger.
5. **degen.** Add `claude-md-cites` under `all-jobs-passed`. Move the pins and add `native-record` to the `ci-done` list. Name the parent rule on line 7 and split lines 7, 35 and 39. Read the live ruleset (item 78). R64: when runners are free: drop the push-to-main trigger.
6. **banchi.** Move the pin and add `claude-md-cites` and `ste-lint`. Cut the restated rules in CLAUDE.md to cites and add one exemption line for the admin wording. Read the roadmap branch and add roster and handoff pointers. Move protection prose to the ruleset form once the merge tool reads rulesets. R64: when runners are free: once-per-batch trim.
7. **q_max.** Move the 9 pins and add a test that no `@<sha>` pin remains. Rewrite D-705 to name `git-never-merge-failing-ci` and replace "primary orchestrator". Add an R44 exemption for D-499 and D-833, or retire them after the pins move. Add `claude-md-cites`. Fill the roadmap data and roster. R64: when runners are free: drop the push-to-main re-run.

Order is by size of the gap as measured above, smallest first. Every lane begins by moving pins, which
needs the stable branch of R42 part 2 to exist first (unmeasured whether it does).

## Source items not carried into a lane

- **Live ruleset reads** (all seven repos, degen's item 78 among them): no API read runs in a cloud session, so one read lane on
  a session on the owner's computer reads the seven rulesets together. It is not one of the seven repo lanes.
- **degen roadmap compare** is folded into its project-ops step, once a lane can fetch `origin/roadmap`.
- **Unused shared actions** the agents listed that a lane above does not name (`ruling-kind` and `ci-done-comment` for
  ios-adblock, `zizmor` for banchi, mailaudit and degen, `silent-undo` and `ruling-kind` for degen, joyous and home): each
  lane decides when it starts whether the repo needs the action. None is dropped as unwanted here.
