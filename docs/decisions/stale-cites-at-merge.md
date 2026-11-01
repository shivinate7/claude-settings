# A PR that removes a name also fixes each prose line that names it

## The ruling

The ste-lint step refuses a pull request that leaves stale prose of one kind: a tracked Markdown line that names a repo file or a Python function that the same PR deleted, renamed or moved. `lint/stale_cites.py` is the check. `actions/ste-lint/run.sh` runs it in scope `changed`, before the markdown-only exit, so a code-only PR is checked too. Every repo that pins the ste-lint action gets it when its pin moves.

Owner, 2026-11-01 16:30 CST, in chat to triage: "make it a standing thing that stale prose never makes it anymore".

- Codes: STALE001, a path the range removed. STALE002, `<file.py> <name>` on one line, where `name` was a def or class in that file at base and is not at head. Python is read with `ast`. JavaScript and shell names are not checked.
- Only names the range removed count. A line already stale at base, for a name the range did not touch, never fires. So the check is never red on work the PR did not do.
- A path matches only at a path boundary. `mods/session-board/hooks/lib.mjs` does not match `hooks/lib.mjs`.
- Left out: `docs/records.md` (generated at merge), each file `.ste-lint-exclude` names, and a line marked `<!-- ste-disable-line STALE001 -->` or `STALE002`. A record that names a removed file on purpose takes the mark.
- Findings have their own exit path. The STE split step makes a finding on an untouched line report-only, and every stale line is untouched by design.
- Cost: one `python3` start and one `git cat-file --batch` start per ste-lint changed-scope run (each PR CI run and each `bin/ste-changed` call). It reads each tracked Markdown file once. It writes no file and starts no lasting process.

## Kind of staleness

Measured risk, 2026-11-01. A sample on main at 84a56038: of 1,176 cites that name a repo path, a path with a symbol, or a script flag in tracked Markdown, 1 named a function that a PR had moved to another file (`docs/debts/notes.md`, note liveness-windows-arm-unproven: `hooks/guard.py _process_start_ms`, now in `hooks/git_reads.py`). Other dead-looking paths were paths in other repos or runtime paths. The debts folder held no debt on stale prose. Notes: stash-export-comment-stale (a stale code comment) and layout-no-such-kind (a "none yet" line).

Not covered: a claim that is wrong in meaning, such as a "Departs from" line that describes main wrongly (the 2026-11-01 16:23 CST incident). No string match can judge meaning. `hooks/prose_judge.py` judges edits inside a decisions folder only.

Kind: build
Home: lint/stale_cites.py
