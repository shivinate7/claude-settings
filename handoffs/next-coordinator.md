# Handoff: next claude-settings coordinator

Written 2026-11-02, after batch #1110 merged. Main is `da8d8073`. The lane list is in `handoffs/next-coordinator-lanes.md`.

Read the two review files too. `handoffs/next-coordinator-review-outcomes.md` says what serves the owner and what strays. `handoffs/next-coordinator-review-terms.md` lists the role-word conflicts. Both date from 13:50 CST, before the sitting rulings. They stand as recorded reviews.

Say the session shape in one line before you start: coordinator, a standing build.

## First moves

1. Run the live-coordinator check. Read every page of `list_sessions`. Look for a session tagged `cs-build:coordinator` and `cs-repo:shivinate7/claude-settings` whose status is not archived. If one is active, do not act as coordinator. Tell the owner.
2. Tag this session `cs-build:coordinator` and `cs-repo:shivinate7/claude-settings`, on its own id.
3. Start triage first. Tag it `cs-build:triage` and `cs-repo:shivinate7/claude-settings`. Triage is standing. It writes the roadmap and the waiting page.
4. Start the batch runner next. Tag it `cs-build:batch-runner`. Brief it to run `get_session` in its own turn, then `~/.claude/bin/merge --role batch-runner`.
5. Start batch 1 (lane list, "Start now"). When a lane's questions are answered, start it. Start lanes in the order the lane list gives.

Triage and the batch runner start together, before any lane session. A lane session runs Opus at medium effort. Start it with `/effort medium` alone, then send the brief.

Triage's first tasks:

- Read the live waiting-page items. Route each answer to its owning session.
- Republish the waiting page as "claude-settings Cockpit". PR #1100 (page title Cockpit) landed.
- Add a roadmap step for the LANDING_TOOLS gap (owner pick a, 2026-11-01 16:23 CST).
- Check the roadmap steps ask-reaches-writer and option-key-guard-gap. Both are Ready.
- Send the coordinator a ready list at each wake.

## Standing rules

- The coordinator never merges. A batch runner runs every merge, under the coordinator's standing merge grant (owner, 2026-11-01 21:34 CST).
- Who started a session sets its merge path. An owner-started solo or one-lane session merges its own PR under that repo's grant. A coordinator-started lane session hands its reviewed branch to the batch runner (owner, 2026-11-02 15:38 CST, fb-1538-1).
- Never merge failing CI. No merge runs while a batch's CI run is in progress.
- The page writer is triage. Where no triage runs, the coordinator writes the page (owner, 2026-11-02 14:02 CST).
- Triage is the only writer of the roadmap (rule `roadmap-one-writer`).
- A coordinator never hands its children to a successor (owner, 2026-11-02 15:24 CST). The previous coordinator's sessions are not yours.
- Inside a standing build the owner started, a coordinator starts lane sessions with no further grant (owner, 15:14 CST). Outside one, each start needs the owner's grant.
- A lane's handoff lives on `handoff/<slug>`, never in the lane PR (owner, 14:26 CST).
- A ruling lands in the PR of the lane that builds it. A ruling with no lane lands in the sitting's ruling PR (owner, 14:15 CST).
- Owner questions reach the waiting page in the same turn (fb-2331-1, fb-2324-1, fb-2326-1, fb-2334-1; rule `questions-go-to-owner`). Ask in chat first. At each wake, if the owner has not answered in chat for 5 minutes, send the question to the page's writer.
- Claude-settings is the law in each child repo. A child may differ only with a cited known exemption and the owner's grant (owner, 2026-11-02 14:02 and 14:11 CST). The coordinator may run child-repo pointer and drift lanes in any child repo (fb-1543-1).
- Write plainly. The repo dropped STE as a named standard (fb-1321-1, fb-1322-1).
- Opus: the deep audit runs on `opus 24h`, until 2026-11-03 16:05 CST. Any other Opus agent needs the owner's grant (`agent-model-cap`).
- The wind-down rulings fb-1231-1, fb-1232-1 and fb-1242-1 told the wind-down session to spawn no sessions. The restart replaces them. The owner has not confirmed this in writing.

## Batch 1

Batch 1 is the first two lanes in the lane list: questions-reach-page-r (PR #1108, head `b0d8b100`) and page-filed-check-r (head `b4661d34`).

- Open a draft PR for page-filed-check-r. It has none yet.
- Check the hold on page-filed-check-r before you mark it ready. The lane list gives the detail.
- Only the integration PR goes ready. Lane PRs stay draft until it merges.

## Deep audit

- Run 1 runs in the previous coordinator's session. Plan: `docs/plans/deep-audit.md` on branch `deep-audit-plan` (head `f0c1e4e6`). The drift pilot script is the extractor base.
- When Run 2 ends, Run 1's findings and its one-home lanes land in this handoff. Run 2 is not recorded as started. This handoff does not name who runs it.
- Owner asks: fb-1602-1, fb-1604-1, fb-1605-1, fb-1605-2, fb-1702-1.
- Do not take over Run 1. The succession rule above applies.

## Goal

"Restart the flywheel" from the freeze record, losing no work (owner, 2026-10-31 14:12 CDT). Now: restart the trio, run batch 1, run the lanes, and land the deep audit's findings when Run 2 ends.

## Working premises

- P1 [read] Main is `da8d8073`. Batch #1110 merged: the sitting rulings, #1107, #1098 and #1100. Checked 2026-11-02 17:37 CST by `git fetch`.
- P2 [ruling] Triage and the batch runner start before any lane session (owner, 15:03 and 15:18 CST; `docs/decisions/session-tiers.md`).
- P3 [ruling] The coordinator never merges (owner, 2026-11-01 21:34 CST; `docs/decisions/session-tiers.md`, Merge grant).
- P4 [ruling] No succession (owner, 15:24 CST; `docs/decisions/session-tiers.md`).
- P5 [read] The owner's Mac session is not reachable from the cloud. The owner pastes prompts. Auto mode refuses `gh` closes, ref deletes (403) and `--base-red-ok`. Source: `get_session` and runner handoffs. Checked 2026-11-02 13:13 CST.
- P6 [ruling] Helper models and efforts: `agent-model-cap`. Helpers keep its table (owner, 17:50 CST, item 59, pick a). A lane session runs Opus at medium effort (owner, 16:15 CST, item 50, pick b; 2026-10-30 15:11 CDT).
- P7 [notes] The feedback guard reads homes from cwd. End each turn in `/home/user/claude-settings`.
- P8 [assumed] A shallow clone at `/root/claude-settings` gives false off-main answers. Unshallow before an ancestry check. Source: banchi handoffs. Not checked.
- P9 [read] 277 remote branches at 13:15 CST. The 136-branch delete list is item 170 (branch-delete-list). Source: `git fetch`.
- P10 [ruling] No session reports its own usage tally. The coordinator reads use with `get_session` (owner, 15:40 CST, item 169, pick a). No usage limit (owner, 2026-11-01 17:56 CST, item 109, pick b).

## Where things stand

- Open PRs: `gh api "repos/shivinate7/claude-settings/pulls?state=open&per_page=100" --jq '.[]|"\(.number) \(.draft) \(.head.ref)"'`. Check other sessions' open PRs before you offer a batch.
- Close as replaced, if still open: #1070, #1104, #1105, #1107, #1098, #1100. The cloud refuses the close. A session on the owner's computer does it (lane list, last lane).
- A scheduled check-in, trig_01L92Gpex5cZYRc1Xj5HQZ3Z, belongs to the previous coordinator. It checked #1110's CI, which is done. Do not reuse it.
- Sitting rulings with a home on main: `docs/decisions/session-tiers.md` and the root `CLAUDE.md` rules.
- No servers run.

## Open owner items

Page: https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx. Collection `items`, field `n`, status open. Read the live items first with ArtifactData. Only triage writes the page, so start triage before you route an answer.

Open:

- 154 (qmax-1011-batch).
- 155 (banchi-codex-rules): no pick. It blocks banchi #1005.
- 166 (newer-run-clears-red): it blocks the red-main lane and the child-repo merges.
- 170 (branch-delete-list): a paste for the owner's Mac.
- 153 (local-reach-plan): triage recorded "last answer b". The lane says no answer was saved. Read it before you route.
- 150 (shivpedia-plan-signoff), 152 (grant-plan-signoff), 130 (3d-first-target), 131 (3d-asset-storage), 91, 163, 167, 168. The handoff gives no titles for 91, 163, 167 and 168.
- 53 (context limit for each tier): the route works. The limit values are not ruled.

Settled, no longer blocking: 109 (no usage limit, pick b), 161 (joyous-68-base-red, pick b, no override), 158 (questions to the page in the same turn), 165 (one excuse line, pick a), 169 (self-reported tally dropped, pick a), 50, 59, 72, 81 and 86.

## Homed earlier (ids kept for citation)

- fb-1449-2, fb-1517-1, fb-1531-1, fb-1532-1, fb-0409-1, fb-0429-1, fb-1716-2, fb-1719-2, fb-1726-1, fb-1737-1, fb-1737-2, fb-1737-3.
- fb-1754-1, fb-1824-1, fb-1843-1, fb-1844-1, fb-1845-1, fb-1846-1, fb-1848-1, fb-1848-2, fb-1850-1, fb-1850-2, fb-1852-1.
- fb-1927-1, fb-1927-2, fb-1927-3, fb-2049-1, fb-2050-1, fb-2051-1, fb-2051-2, fb-2054-1, fb-2057-1, fb-2102-1, fb-2105-1.
- fb-2106-1, fb-2107-1, fb-2108-1, fb-2132-1, fb-2134-1, fb-2134-2, fb-2222-1, fb-2222-2, fb-2223-1, fb-2237-1, fb-2237-2.
- fb-2243-1, fb-2252-1, fb-2254-1, fb-2255-1, fb-2257-1, fb-1052-1, fb-1100-1, fb-1112-1, fb-1149-1, fb-1154-1.
- fb-1041-2 (child repos cite records; landed in #1098).

## Files and commands

- Lane list: `handoffs/next-coordinator-lanes.md` on this branch.
- `handoffs/load-balance-findings.md` on this branch is outside this rewrite. Its status is unknown.
- Lint: `./bin/verdict ./bin/ci-job checks --lint`.
- Verify a file on origin: `git fetch -q origin <branch> && git cat-file -e <sha>:<path>`.
- Page items: ArtifactData query `items` where `n` is in the list you need.
- CI state: `gh api repos/shivinate7/claude-settings/commits/<sha>/check-runs --paginate --jq '.check_runs[]|"\(.status) \(.conclusion) \(.name)"'`.
- Checkouts: /home/user/{claude-settings,q_max,banchi,degen,joyous,mailaudit}.
- Not carried over: the previous coordinator's scratch files and inbox. The designer-gap notes (fb-1510-1) and the drift workflow script stay in that session. Copy what you need into git on a lane branch.
