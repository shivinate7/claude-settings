# c43 remainder: file the dropped-lane debt

Cloud build thread brief. Build advisor, Oct 26, against claude-settings main 3f71d6b. Solo, records only.

Lane 2 of c43 (a SubagentStop check that blocks an agent reporting with a live watcher) was dropped
by shiv on Oct 26: its try blocked 248 of 1,787 real stops by mistake. Its code sits on branch
stop-blocks-live-tasks (b8feeb52). Lane 1 landed in #574 (agents stop their watchers before they
report).

Task: write one debt in claude-settings debts/, in the store's own format (read debts/README.md and
two existing debts first). Slug: agent-reports-with-live-watcher. Content: the gap (no check stops an
agent that reports with a live watcher), the dropped try and its false-block count, the branch, and
the Retire line: reopen as a check only if leftover watchers keep waking parents. Point it to
decision agents-stop-their-watchers if one exists (git grep). Update any index the store keeps
(docs/records.md is rebuilt at merge; do not hand-edit it unless the store says so).

Base: main. One commit, PR stops at green; merge waits for c53 or shiv's merge.py run.
Report: 10 lines max, with the PR.
