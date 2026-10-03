# compliance-check probes

Run each from the child's root. `$P` is the parent clone. A probe that cannot run is
`unknown`. Every probe reads only.

## Parent lints that accept a child path

| Lint | Command | Reads |
| --- | --- | --- |
| `ste_lint.py` | `python3 $P/lint/ste_lint.py --fail-on error --quiet <child *.md>` | STE errors in child prose |
| `check_record_slugs.py` | `cd <records parent> && python3 $P/lint/check_record_slugs.py decisions/*.md deferred/*.md` | slugs over 32 characters |
| `check_agent_models.py` | `python3 $P/lint/check_agent_models.py .claude/agents/*.md` | a Haiku model in agent frontmatter |
| `check_silent_undo.py` | `python3 $P/lint/check_silent_undo.py --repo . --history` | lost lines and reversals on main |

`check_record_slugs.py` matches only paths that start with `decisions/` or `deferred/`. For a
child that keeps records in `docs/decisions/`, run it from `docs/`.

These lints read the parent tree only, and cannot target a child: `rule_audit.py`,
`check_landed_dirs.py`, `check_unknown_reads_contract.py`. `md_sweep.py`, `ste_gate.py` and
`report_gate.py` are hooks: they already run in the child's sessions. `ruling_census.py` reads
session transcripts, not a repo.

## Probes per group

| Group | Probe | In shape when |
| --- | --- | --- |
| Outcomes | Read the child `CLAUDE.md` and README first screen. Run `ste_lint` on both | rules name the person served; README passes `fresh-prose` |
| Outcomes | `grep -c "rule:" CLAUDE.md`; look for a check per local rule | each local rule has a hook, test, or CI step |
| Roles | `git log --oneline -40 origin/main` and `git branch -r` | test commits or `tests/*` branches land before product commits |
| Roles | `cat .claude/settings.local.json` | no stale model raise; any raise has `_subagentCapUntil` in the future |
| Parallelism | `git worktree list`; `grep -n worktrees .gitignore` | work runs in worktrees; `.claude/worktrees` is ignored |
| Shared trees | `git stash list \| wc -l` | 0 entries |
| Shared trees | `.claude/launch.json`, dev scripts | each checkout can set its own port and data |
| Git | `gh pr list --state merged --limit 20` and `git log --first-parent --no-merges --oneline -20 origin/main` | main moves only by PR |
| Git | `gh api repos/{owner}/{repo}/branches/main/protection` | the answer is known. A 404 is a known answer: no protection |
| Git | records folders, slugs lint | one file per record, one folder per kind, slugs of 32 or fewer |
| Git | `check_silent_undo.py --history` | no lost lines |
| Verification | `ci-hygiene` skill on `.github/workflows/` | no top finding |
| Verification | list the screens, if any, and the sizes and themes they ship in | a check per screen |
| Verification | `grep -rn "sleep" .github/ scripts/` | no waiter loop |
| Tokens | none: session practice | `n/a (session)` |
| Building | `git ls-files \| grep -i test` against product files | each product module has a test |
| Building | designs in `docs/` or `plans/` with no record | each design has a record, or is marked abandoned |
| Speak plainly | `grep -rnE "\bD[0-9]+\b" --include=*.md .` with no gloss beside the id | each cited id has a short gloss |
| Output | `ste_lint` totals on the child's `*.md` | 0 errors |
| Reports | none: `report_gate.py` covers it | `parent-covered` |
