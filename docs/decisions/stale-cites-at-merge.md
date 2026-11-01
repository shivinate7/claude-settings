# A PR that removes a name also fixes each prose line that names it

## The ruling

The ste-lint step refuses a pull request that leaves stale prose of one kind. The kind is a tracked Markdown line that names a repo file or a Python function that the same PR deleted, renamed or moved. `lint/stale_cites.py` is the check. `actions/ste-lint/run.sh` runs it in scope `changed`, before the markdown-only exit, so a code-only PR is checked too. Every repo that pins the ste-lint action gets it when its pin moves.

Owner, 2026-11-01 16:30 CST, in chat to triage: "make it a standing thing that stale prose never makes it anymore".

- Codes: STALE001, a path the range removed. STALE002, a name cited as "`file.py` `name`" (backticked name) or "(file.py name)" on one line, where `name` was a def or class in that file at base and is not at head. A bare word after a path is never a cite. Python is read with `ast`. A name counts when it is module-level (also under a module-level if or try) or a def directly in a module-level class; a def nested in a function does not. JavaScript and shell names are not checked.
- Only names the range removed count. A line already stale at base, for a name the range did not touch, never fires. So the check is never red on work the PR did not do.
- A path matches only at a path boundary. `mods/session-board/hooks/lib.mjs` does not match `hooks/lib.mjs`.
- Left out: `docs/records.md` (generated at merge), each file `.ste-lint-exclude` names, and a line marked `<!-- ste-disable-line STALE001 -->` or `STALE002`. A record that names a removed file on purpose takes the mark.
- Each Markdown file is read as committed at head, never from the working tree, through the same `git cat-file --batch` process. A byte that is not UTF-8 reads as a replacement character and the file is still checked.
- A base that does not resolve (a shallow clone with no history) is unknown, not a finding. The check prints `stale-cites: unknown, ...`, names fetch-depth 0, and exits 0, so a repo that pins the action and checks out shallow is not red at its pin move (owner-lane call, 2026-11-01).
- `FAIL=false` is honored: the findings print and the step exits 0.
- Findings have their own exit path. The STE split step makes a finding on an untouched line report-only, and every stale line is untouched by design.
- A touched `.py` file that does not parse at base or head is unknown the same way: `stale-cites: unknown, <file> ...`, and it alone keeps the exit 0.
- Cost, per ste-lint changed-scope run (each PR CI run and each `bin/ste-changed` call): one `python3` start. Git starts 3 (`rev-parse`, `merge-base`, `diff`) when the range removes or renames no path and touches no `.py` file. A touched `.py` file adds one `git cat-file --batch`. A removed path or def adds `ls-tree` and that `cat-file --batch`, so 5 at most. Each tracked Markdown file is read once, and only when something was removed. It writes no file, no `.pyc` either, and starts no lasting process. `CostTests` in `lint/test_stale_cites.py` proves it.

## Kind of staleness

Measured risk, 2026-11-01. A sample on main at 84a56038: tracked Markdown held 1,176 cites that name a repo path, a path with a symbol, or a script flag. One named a function that a PR had moved to another file (`docs/debts/notes.md`, note liveness-windows-arm-unproven: `hooks/guard.py _process_start_ms`, now in `hooks/git_reads.py`). Other dead-looking paths were paths in other repos or runtime paths. The debts folder held no debt on stale prose. Notes: stash-export-comment-stale (a stale code comment) and layout-no-such-kind (a "none yet" line).

Not covered: a claim that is wrong in meaning, such as a "Departs from" line that describes main wrongly (the 2026-11-01 16:23 CST incident). No string match can judge meaning. `hooks/prose_judge.py` judges edits inside a decisions folder only.

Kind: build
Plan: docs/decisions/stale-cites-at-merge.md#the-ruling (all)
Home: lint/stale_cites.py
