# Plan: how good tests and CI are made, how far the repos are, and how to close the gap

Roadmap step `test-ci-standard` (the test and CI standard). The step record is
`roadmap/data/steps/test-ci-standard.json` on branch `roadmap`. The owner asked for it on
2026-11-01 16:20 CST. Read-only research made it on 2026-11-01: two web lanes, one lane on this
repo's own rules, and one review lane per repo (banchi, degen, home, ios-adblock, joyous,
mailaudit, q_max).

The step note (roadmap step `test-ci-standard`) carries the owner's ruling of 2026-11-01 12:23 CST:
a practice joins the standard only when it makes the build better, never as optional load on
builders. Each practice below names the harm it stops.

## The standard

Each row is one practice, the harm it stops, its outside source, and its home in this repo.

| Id | Practice | Harm it stops | Source | Home here |
|---|---|---|---|---|
| S1 | Red is red. Fix a red main at once. An unknown result is red. | People learn to ignore red, and real failures ship. | [Fowler, CI](https://martinfowler.com/articles/continuousIntegration.html); [DORA, CI](https://dora.dev/capabilities/continuous-integration/) | `git-never-merge-failing-ci` (never merge failing CI); `ci-unknown-is-red` (decision: an unknown CI read is red); `no-merge-onto-red-main` (decision: no batch merges onto a red main) |
| S2 | Each shipped platform runs its tests in CI, or in a named local gate with a recorded run. | A defect that exists on one platform only ships. | [GitHub, matrix jobs](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow); Fowler, CI (production-like test) | `verification-green-proves-only-its-fixtures` (a green check proves only its platform and its fixtures); `test-strategy-reset` (decision: tests prove outcomes and never fail on runner speed) |
| S3 | CI tests the artifact and the dependencies that ship. | CI is green on a build that nobody runs. | [Google, hermetic servers](https://testing.googleblog.com/2012/10/hermetic-servers.html); [Bazel, hermeticity](https://bazel.build/basics/hermeticity) | none |
| S4 | A test proves behaviour that the user sees, through the public interface. A source-text scan is not the only proof of a screen. | Tests break on a refactor and stay green when the user's screen breaks. | [SWE at Google ch. 12](https://abseil.io/resources/swe-book/html/ch12.html); [Dodds, implementation details](https://kentcdodds.com/blog/testing-implementation-details); [SWE at Google ch. 13](https://abseil.io/resources/swe-book/html/ch13.html) | `test-strategy-reset` |
| S5 | Each new test is seen red on the old code before the fix. A bug gets a failing test first. | A test that cannot fail goes green and proves nothing. | [Beck, Canon TDD](https://newsletter.kentbeck.com/p/canon-tdd); [Claude Code best practices](https://code.claude.com/docs/en/best-practices) | `roles-each-layer-proves-once` (each layer proves a change once); `builders-cannot-edit-tests` (decision: builders cannot edit tests) |
| S6 | An agent never edits a test to match the code's output. A separate reader checks each assertion. | Agents special-case tests or weaken them to go green. | [Claude 3.7 system card, s. 6](https://www-cdn.anthropic.com/9ff93dfa8f445c932415d335c88852ef47f1201e.pdf); [METR, reward hacking](https://metr.org/blog/2025-06-05-recent-reward-hacking/); [ImpossibleBench](https://arxiv.org/abs/2510.20270); [LLM oracles drift](https://arxiv.org/html/2410.21136v1) | `outcomes-tests-are-statements` (a failing test is a claim, not law); `builders-cannot-edit-tests` |
| S7 | Measure test strength by mutation score on changed lines, not by line coverage. | Weak tests pass. Coverage counts code that ran, not code that was checked. | [Inozemtseva, ICSE 2014](https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf); [Petrović, ICSE 2021](https://arxiv.org/abs/2103.07189); [Google, mutation at scale](https://research.google/pubs/practical-mutation-testing-at-scale-a-view-from-google/) | `verification-trust-guard-after-red` (trust a guard once it goes red on its defect; guards only) |
| S8 | A skip is counted and shown, never read as a pass. | A test that never runs looks green. | `house rule` | `test-strategy-reset` rule 1 |
| S9 | Fix a flaky test at its cause. No blind retry and no fixed sleep. Quarantine only with a record and a deadline. | Real failures get dismissed as flakes. | [Google, flaky tests](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html); [Luo and co-authors, FSE 2014](https://huang.isis.vanderbilt.edu/cs8395/paper/flakytest.pdf); [Fowler, non-determinism](https://martinfowler.com/articles/nonDeterminism.html) | `test-strategy-reset` |
| S10 | Check each screen rendered, at each shipped size and theme. Visual baselines come from one fixed environment. | A colour, spacing or overflow break reaches the user. | [Playwright, snapshots](https://playwright.dev/docs/test-snapshots); [Chromatic, visual tests](https://www.chromatic.com/docs/visual/) | `verification-screens-verdict` (check each screen and give a verdict per screen) |
| S11 | Feedback in about 10 minutes. Each job cap is about 2 times its slowest run. | Slow feedback makes larger, riskier merges. | [Fowler, CI](https://martinfowler.com/articles/continuousIntegration.html); [DORA, CI](https://dora.dev/capabilities/continuous-integration/) for the 10 minutes; the 2x cap is a house rule | `ci-job-caps` (decision on each CI job's time cap) |
| S12 | One `all-jobs-passed` job, with `if: always()`, reads each job result and is the one required check. | A skipped or failed job reads as a pass, or a required check waits for ever. | [GitHub, required checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks); [GitHub, contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) | `same-check-kinds` (decision: every repo runs the same kinds of checks); `main-branch-protection` (decision: branch protection on main) |
| S13 | Pin each action by full commit SHA. Use a read-only token. Set `persist-credentials: false`. | A moved tag runs other code (tj-actions, March 2025, 23,000+ repos). | [GitHub, hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions); [Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md); [GitHub advisory GHSA-mrrh-fwg8-r2c3](https://github.com/advisories/GHSA-mrrh-fwg8-r2c3) | the `ci-hygiene` skill, step 7 |

Left out, because no repo here has a named harm they stop: DORA metrics as targets, test selection
by prediction, merge queues.

## How far each repo is

Read on 2026-11-01 from each repo's main head. "unmeasured" means that the read could not run.
"met" means that the repo meets the gold standard.

| Id | Gold standard | banchi | degen | home | ios-adblock | joyous | mailaudit | q_max |
|---|---|---|---|---|---|---|---|---|
| S1 | Main green; each red explained | history unmeasured (proxy 403) | main red since 2026-10-31, CI runs 1746 and 1747 | met: 15 of 15 runs green | met: 21 of 22, the red was a planned proof | 3 reds in 30 runs: 1 planned proof, 2 with no cause and no record | unmeasured (proxy 403) | 17 of 18 in a 2-day window; 1 red cause unread |
| S2 | Each shipped platform tested | Ubuntu only; owner runs it on a Mac | about 780 of 1037 test files (Swift) never run in CI | iOS runs on the first iPhone, not the Duo | one iPhone simulator; iPad unmeasured | no real iOS Safari | iOS app build and 136 UI tests run in no CI job | 7 Windows-only tests never run |
| S3 | CI tests what ships | dev server in CI; built `app/dist` ships; the built-bundle spec skips on each PR | not met: Swift app not built in CI | add-on tested with pip packages on x86; ships Alpine packages, also on aarch64 | partly: extensions not tested as shipped | met | not met: Worker tested under node, not workerd | met |
| S4 | Behaviour tests; no scan-only screen proof | some tests restate the rule they test | 160 Swift tests read view source | 38 scan files; `XCTAssertTrue(true)` in SmokeTests.swift:4 | met (5 sampled), but BlockerListTests :23-45 pin rule text | met (5 sampled); one test checks a reason code, not behaviour | 3 tests that cannot fail (debt) | 98 of 562 files read source text (debt) |
| S5 | Red-first proof per new test | prose only | prose only; CLAUDE.md:39 says no check | done by habit: 17 red proof runs of 29; no check | prose only | a comment only | prose only | prose only |
| S6 | Test edits checked apart from code | not read | not read | not read | not read | not read | not read | not read |
| S7 | Mutation score on product code | guards only, off CI | none | none | none | none | none | none |
| S8 | Skips shown | 9 skips, 2 are shelved guards; no `forbidOnly` | partly: no skip count shown; conditional skips, `forbidOnly` in CI | met: 0 skips | keychain tests skip on each CI run | partly: no skip count shown | partly: no skip count shown | 17 skips |
| S9 | Flakes fixed at cause | a 1-in-10 red with no record | 6 fixed sleeps (debt) | a wait raised to 120 s with no record | partly: a retry bandaid in pin-bump.yml:43 | met | 319 real-time sleeps; a flake and a hang open | 3 flaky debts |
| S10 | Screens at each size and theme | 390 and 720 px never run (banchi debt DEBT77) | 2 sizes, 2 themes, geometry and a11y only; no pixel check | no screen test | no screen test | light only; no width 415-1279 | Chromium only; no WebKit | browser tier runs on dispatch only; its one run was cancelled |
| S11 | About 10 min | shard claim 140-297 s, unmeasured | median 15.6 min | met: 5.4 min | met: 6.2 min | met: 7 min; build peak 8.25 of 10 min | repo claim 670 s for screens, unmeasured | median 24.1 min; shards 12-23 min against 4-8 documented |
| S12 | One required rollup | rollup met; required check unmeasured; records disagree | rollup met; required unmeasured | rollup met; required unmeasured | rollup met; required unmeasured | rollup met; required unmeasured | rollup met; required unmeasured | rollup met; D-537 (q_max decision, no branch protection) says none, stamp.json says a required check |
| S13 | SHA pins | met; shared pins 2026-10-29 | met; shared pins 2026-10-29 | met; two shared pins | met; shared pins 2026-10-29 | met; four shared pins | met; shared pins 2026-10-29 | met; two shared pins |

claude-settings itself meets S1, S12 and S13 by guard and CI. Its own gaps:

- `agents/test-author.md:17-18` lets a test pass "after the build" with no red run. CLAUDE.md rule
  `roles-each-layer-proves-once` asks for red on the old code.
- At commit and push, the guard only logs a builder's test edit (`hooks/guard.py:1688-1695`). Three
  sessions routed around the write refusal on 2026-10-31 (decision `guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent).
- `bin/verdict` prints PASS for a run with skips (debt `verdict-skip-reads-pass`).
- 60 `time.sleep(` calls in tests; no check enforces the no-fixed-sleep rule.
- Stale records: `same-check-kinds.md:20` says there is no `all-jobs-passed` job;
  `lint/rule_mechanisms.json:215` calls `git-never-merge-failing-ci` unmechanized; cap
  comments cite a missing measured-time table.
- The test-author and the round-1 reviewer run Haiku. They write and judge the red record. Their
  quality is unmeasured (`agent-model-cap`, the model-per-role table).

## The plan, ranked by harm avoided

Each lane runs in the repo named. A lane in claude-settings reaches every repo.

| Rank | Lane | Repo | Closes | Harm avoided | Done when |
|---|---|---|---|---|---|
| 1 | Fix the shared Playwright setup for Ubuntu 26.04 | claude-settings, then each repo pin | S1 | degen main is red and its web suite does not run; banchi, joyous and q_max pin the same playwright-setup action | the browser job is green on main in degen, banchi, joyous and q_max |
| 2 | Close the red-first gap: fix the test-author wording, and make the lane PR carry the red run of its new tests on the old code | claude-settings | S5 | a test that cannot fail, in every repo | a check refuses a lane PR with new tests and no red run |
| 3 | Make the commit-time builder test-edit check refuse, not log | claude-settings | S6 | an agent edits a test to match its code, in every repo | a builder commit that edits a test is refused, and a test shows it red first |
| 4 | Show skips: `verdict` prints a SKIP count, and the shared code-check reports skips | claude-settings | S8 | ios-adblock keychain tests and banchi guards never run, and CI looks green | a test of `verdict` with a skip prints SKIP |
| 5 | Name where each shipped platform is tested | degen, mailaudit, banchi, home, ios-adblock | S2, S3 | the main shipped product has no CI proof | each shipped platform has a CI job or a named local gate, with a green run recorded on the last merge |
| 6 | Mutation score on changed lines, report only, at batch CI | claude-settings template, then joyous and q_max | S7 | weak tests pass in every repo | the batch run posts a score; the owner rules on a gate after 2 weeks |
| 7 | Enable banchi phone specs (DEBT77) | banchi | S10 | a sideways scroll at 390 px reaches the owner's phone | the 390 and 720 px cases run in CI |
| 8 | Remove tests that cannot fail | home, mailaudit | S4 | false green | `XCTAssertTrue(true)` is gone; the mailaudit debt is closed |
| 9 | A record for each known flake, with a cause and a deadline | banchi, home, mailaudit, joyous | S9, S1 | real failures dismissed as flakes | each flake and each unexplained red has a debt with an owner and a fix date |
| 10 | Read live branch protection and fix the records | each repo | S12 | a merge with no required check | the live required checks of each repo include all-jobs-passed |
| 11 | Move each repo's shared action pins to one current main commit | each repo | none (pin drift) | mixed, stale shared code in CI | one pin per repo |
| 12 | Re-measure q_max shards and caps | q_max | S11 | slow feedback; caps set on stale figures | each shard's slowest run is under 10 minutes |
| 13 | Fix the stale claude-settings records | claude-settings | none | readers trust a wrong record | `docs/decisions/same-check-kinds.md`, `lint/rule_mechanisms.json`, the cap comments in `.github/workflows/checks.yml` and `agents/test-author.md` are fixed |

## Owner questions

These go to triage as page questions. Page items 133, 134 and 135 hold them. Lanes 5, 6 and 7
(the rows ranked 5, 6 and 7 above) wait for them. The other lanes need no answer.

1. Swift tests in CI (lane 5). A macOS runner costs about 10 times a Linux runner
   ([GitHub billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)).
   Degen has a ruling against a self-hosted runner (2026-10-11).
2. Mutation score (lane 6): report only, or a gate after the pilot.
3. Banchi phone specs (lane 7): DEBT77 holds the owner's ruling to keep them off.
