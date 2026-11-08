# A builder's reported files are checked in the pushed head before review

## The ruling

`lint/check_report_in_head.py` is the one home. It reads the one `Files:` line of a builder's report and checks each path against the diff of the pushed branch head (`refs/heads/<branch>` on origin, never the local tree).

The mistake (incident, PR 1179, 2026-11-08): a hook refused a builder's Bash call, so an edit never applied. The builder reported it anyway. A test-author's red test caught it.

The harm it stops: a review that reads a change that is not there.

The lane rule: before a lane spawns the reviewer, it runs `python3 lint/check_report_in_head.py --branch <name>` on the builder's report.

- A 0 passes. The lane spawns the reviewer.
- A 1 sends the builder back. The output names each reported path that is not in the diff.
- A 2 is reported as unknown (branch not on origin, git failure, no `Files:` line, an empty one, or an absolute path). The lane does not call it a pass.
- The reviewer brief carries the verdict. The reviewer never re-runs the check (`roles-each-layer-proves-once`, each layer proves a change once).

Scope: reported but not in the diff only. A changed file the report leaves out is not judged.

Cost: 3 git calls per run (one fetch of one branch, one rev-parse, one diff). It writes no file. A lane runs it once per builder report, before review.

Why: the builder's report is a claim. The pushed head is the only state the reviewer reads.

Kind: process
Home: lint/check_report_in_head.py
