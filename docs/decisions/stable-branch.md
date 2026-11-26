# The stable branch follows each green push run of main

## The ruling

Sessions and installers run from a branch named `stable` on origin. Restart plan entry R42 part 2 sets this. The owner approved that design 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST.

Stable follows each green push run of main. Owner, 12:59 CST Nov 16: "Just keep stable matching main for now then if that's easiest / Probably is easiest" and "Like keep that as a match every time main merges stable goes ahead too".

- Trigger: `workflow_run` on the checks workflow's completion, for a run on main that ends in success. Two events count: `push` and `schedule` (the daily). A manual (`workflow_dispatch`) run moves nothing, since a manual run may not be the daily's head. Home of the move: `actions/stable-mover/run.sh`.
- Move: fast-forward `stable` to that run's head sha. A move that is not a fast-forward is refused. The job never force-pushes.
- A red, cancelled or unknown run leaves `stable` where it is.
- A green push run covers the Linux fast jobs only (decision `push-skip-on-proven-tree`, which lets a push skip checks a passing PR run covered). So `stable` can sit on a commit whose Windows and mutation jobs have not run. The next daily covers them. The owner accepted this for now.
- Installers and the merge tool read `stable`. Their fallback is decision `stable-fallback-warn`: they fall back to main when stable is missing.

Alternative not taken: a last job in the checks workflow, on push to main, in place of a separate workflow file. Refuter, 2026-11-11 22:58 CST, simpler route. The design names the `workflow_run` trigger.

## Owner ruling: route B, stay on stable with a PR check

Owner ruling fb-1427-1, 14:27 CST Nov 25 2026, in the consultant's chat, on option "(b) Stay on stable + a PR check": "this is approved." This is route B.

The owner's purpose, 13:12 CST Nov 25: "Stable, is so that way every session doesn't break if something lands on main too quickly before all runs were checked to be green ... is to ensure that the version of claude settings my sessions are using has been fully vetted for holes".

The owner, 13:25 CST Nov 25: "I think I approved it though, as long as it accomplishes what I actually set out to have" and "however that's accomplished, yes it's up to you so feel free".

Route B, widened 13:58 CST Nov 25 by the Sim Manager under the owner's 13:25 grant. This is the Sim Manager's decision, not an owner quote.

- The merge tool keeps running from `stable`. The recovery switch `CLAUDE_SETTINGS_REF=main` stays. It makes installers read main, not `stable`.
- The PR check runs stable's readers on each pull request's tree. It covers every main file the installed copy reads: `.github/stamp.json`, the records page, and the parsed config. Job `checks` runs it in two steps: a fixture suite for the check, and the check itself, `lint/check_stable_readers.py`. It fails when a stable reader refuses the tree, or reads it differently from the PR's own reader. It judges the records page only when the PR changed that page.
- A PR that changes no data file gets each difference waived, with one printed line per key. The data files are `.github/stamp.json`, `.github/workflows` and the records page, compared with the base ref. If the PR changes any one of them, no difference is waived. A refusal is never waived.
- A PR head config value the stable tool cannot read is refused: `head_config_refusal` in `merge/merge.py`, under decision `config-lands-after-its-reader`. It runs in the lane lint, the ready path and confirm, before any claim or push. It does not run under `--fast-checks`.
- One reader for the guard and the tool. This replaces the split at `hooks/guard_merge.py` lines 195-215.
- Cost accepted: format changes wait for stable. Lag shortens through CI cuts and runner capacity.

Dropped options:

- Move at merge: `stable` moves at each merge, on a proven tree. Only 6 of 80 merges qualify.
- Tolerant readers: readers that accept values they do not know. Unsafe for most keys.

74 of 80 merged trees were untested.

Why: stable keeps sessions off changes that are not vetted. Stable moves on a push or daily run that ends with success, by fast-forward only, and reads no job of the run. A red run never moves it. A green run that skipped a suite does (see the green push run bullet above). Restart plan entry R42 part 2.

Incident: PR #3863 (branch `confirm-needs-proof`) and PR #3871 (branch `lint-runs-listed-suites`) each put a stamp value on main together with its reader. Stable refused main's stamp until stable moved. Debt `old-merge-tool-refuses-stamp`: an old merge tool refuses main's `stamp.json`. <!-- glossary-ok: the debt's real id, as docs/records.md lists it -->

Cost per PR run, as measured: 2.8 s, or 7.8 s with the page proof (n=1 each). At most six python starts: four without the page proof (this script, a probe of each tree's readers, and the stable records generator), and two more with it, one in each probe.

## The guard

The merge guard (`hooks/guard_merge.py`) checks the stamp's `merge.requiredChecks` string against the pinned strings of the installed merge tool. A string that tool does not pin is an unknown pin. The merge check refuses the head as unknown and names the string. Its remedy offers waiting for a tool that pins the string, or landing that string's reader. A push to a ready pull request under an unknown pin is judged as under the protection pin, and the guard prints one warn line on stderr that names the string. On a ready mark whose page read is unknown, the refusal names the followed ref (`stale_install.followed_ref`, `origin/stable` by default) when the installed copy is behind it.

Single reader: open. Route B makes the guard and the tool share one reader (see route B). Until then the guard loads the pinned copy's reader, `merge/merge.py` beside the hook's real path. The tool runs the followed ref's tree: `merge/launch.py` checks out `origin/stable` in a temporary worktree. So the guard's pin list can differ from the tool's when the installed copy and the followed ref differ.

Kind: process
Home: docs/plans/restart-plan.md
