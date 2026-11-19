# Handoff: lane settings-docs-stale-switch-text, 2026-11-19 00:25 CST

Repo: shivinate7/claude-settings. Lane branch: `lane/repo-claims-live`. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Roadmap step: `child-repos-decision-claude-md-gap`.

## Open PRs

- #3471, draft, open, not merged. Head `8d67238307d228e04db23a08bf3dc9d1c28b8e7b` (read from REST 2026-11-19 00:25 CST). Its base was `a97e35e2` when last read; main has moved on (`bd0759f8` at 00:25 CST).
- Lane lint PASS comment 6892633531 (head 8d672383). Review record comment 6892637662 (head 8d672383). `merge --reviewed` read it done at 2026-11-15 03:57 CST (not re-read since).
- Earlier comments on the PR: lint 6891400311 (04aeb3cd), records 6891407379 and 6891409271, lint 6892584293 (50b0fa89).

## Done

- `docs/decisions/all-repos-switch-together.md`: adds ruling `own-820-c-five-repos` (owner, 00:19 CST Nov 14) and `own-821-a` (owner 02:36 CST Nov 14, q_max one-lane batch branch). Seven repos granted per-lane merge; live state unmeasured. Both rulings sit on origin/roadmap only.
- `docs/decisions/draft-until-reviewed.md`: State rewritten to the same list.
- `docs/decisions/stable-branch.md`: State rewritten (stable exists on origin and lags main; `stable.yml` moves it only on a green push run of checks on main; 211 behind at 2026-11-15 01:14 CST).
- `CLAUDE.md`, four rule sentences: roles-third-round-steps-up (round 1 Sonnet on a guard or check change, Haiku otherwise), parallelism-keep-going (coordinator compliance exception; undoable acts still ask), git-integration-branch-merge (per-lane merge by repo, q_max one-lane batch, else one integration PR), questions-go-to-owner (box only in a repo with no page).
- Plain merge of main into the branch once (1ba44ef5). No force push, no rebase.

## Unfinished

- The second PR, not started: `GLOSSARY.md:29`, `docs/decisions/stable-fallback-warn.md:7`, `skills/ci-hygiene/SKILL.md` lines 59, 61, 63, 161. Notes, no edit yet: `agents/reviewer.md:75`, `GLOSSARY.md:40` fix-verifier row, `docs/decisions/questions-go-to-owner.md:7`.
- Main's CLAUDE.md rule text has changed since 2026-11-15 (new owner rulings in `roles-orchestrator-never-builds`, `roles-sonnet-is-the-ceiling`, `roles-third-round-steps-up`, `git-red-main-reverts`, read from this session's instruction reload). #3471's four CLAUDE.md edits were made against the Nov 15 text. They need a merge of main and a re-read of each sentence before any further step. Unchecked: whether the merge conflicts.
- Hold since 2026-11-15 11:10 CST: owner ruling `own-mechanical-before-cleanup` (11:07 CST Nov 15, via the consultant). A cleanup of stale prose runs only after the mechanical check that keeps it fresh has landed. No check was named as landed. The lane resumes only when the coordinator says one landed.

## Next step

When a mechanical check lands and the coordinator resumes the lane: fetch main, merge main into `lane/repo-claims-live` (plain merge), re-read each of the seven edits against main, fix text, fix check, lane lint without `--lint-unknown-ok`, new review record, hand in.

## Refused or blocked acts

- Round-1 Sonnet reviewer on CLAUDE.md: the spawn guard refused it (CLAUDE.md is not a guard path). Ran Haiku. No override asked.
- Lane lint read `unknown`, not a pass, while the touched-tests draft run was unfinished; re-run each time.
- `pgrep -af` refused by the process-args guard; no process list was printed.

## Owner rulings this lane holds

- `own-820-c-five-repos` (00:19 CST Nov 14) and `own-821-a` (02:36 CST Nov 14): both on origin/roadmap, status open there.
- `own-degen-home-switch-now` (22:13 CST Nov 13): degen and home.
- `own-mechanical-before-cleanup` (11:07 CST Nov 15): the hold above. Relayed by the coordinator at 11:10 CST; this lane did not read it on roadmap.
- Q2 (ready timing) in the five repos is an inference from the grant; no owner words name it.

## Agents

- record-writer `a511115092e88e858` (haiku): worktree branch `worktree-agent-a511115092e88e858`, at `8d672383`. Wrote all text edits.
- Reviewers: `a50fd257b379e1a27` (docs round 1, haiku), `a85f3c0bbc31c1826` (docs round 2, sonnet), `ab4630e9ec5967e4c` (docs round 3, sonnet), `aa8893294f9269f62` and `a66fb14f8ecbf8775` (fix verifiers, sonnet), `a5287db7ca968be7b` (CLAUDE.md round 1, haiku, worktree at `50b0fa89`), `a761cd8556df49237` (CLAUDE.md round 2, sonnet, worktree at `8d672383`).
- Local worktrees under `.claude/worktrees/`: the agent ones above, `lane-claims` (branch `lane/repo-claims-live`, local head `1ba44ef5`, behind origin), and `handoff-slug` (this branch). All agent branches hold nothing beyond origin's lane branch.
- No agent is running now.

## Pointers

- Inbox file: `/root/.claude/handoffs/ff97b1de-a82c-5632-bae7-ec190292fd7f.inbox.md` (items fb-0114-1, fb-0114-2).
- Scheduled check-ins: none open that this lane knows of.
