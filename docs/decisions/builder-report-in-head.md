# A builder's reported files are checked in the pushed head before review

## The ruling

`lint/check_report_in_head.py` is the one home. It reads the one `Files:` line of a builder's report and checks each path against the diff of the pushed branch head (`refs/heads/<branch>` on origin, never the local tree).

The mistake (incident, PR 1179, 2026-11-08): a hook refused a builder's Bash call, so an edit never applied. The builder reported it anyway. A test-author's red test caught it.

The harm it stops: a review that reads a change that is not there.

The lane rule: before a lane spawns the reviewer, it runs `python3 ~/.claude/lint/check_report_in_head.py --branch <branch> --report <file>` on the builder's report. That is the installed copy, so a lane in another repo runs it too.

- A fix round passes `--base <last reviewed head>`, so a refused fix-round edit to a file round 1 already touched still fails.
- A 0 passes. The lane spawns the reviewer.
- A 1 sends the builder back. The output names each reported path that is not in the diff.
- A 2 is reported as unknown (branch not on origin, git failure, no `Files:` line, an empty one, an absolute path, or a report that is not UTF-8). The lane does not call it a pass.
- The reviewer brief carries the verdict. The reviewer never re-runs the check (`roles-each-layer-proves-once`, each layer proves a change once).

Scope: reported but not in the diff only. A changed file the report leaves out is not judged.

Cost: 3 git calls per run (one fetch of the branch and the base, one rev-parse, one diff). The fetch updates FETCH_HEAD and the remote-tracking refs it fetches, nothing else. A lane runs it once per builder report, before review.

One home: the check keeps its own diff call, not `changed_paths` in `hooks/guard.py`. That helper runs `git -C <dir>` with a 10 s timeout and hides git's error text. The suite pins the call count by subcommand and the check prints git's error.

Why: the builder's report is a claim. The pushed head is the only state the reviewer reads.

Kind: process
Home: lint/check_report_in_head.py
