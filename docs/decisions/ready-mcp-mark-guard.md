# A ready mark by MCP needs a ready pass on the head

## The ruling

Question: may a session mark a pull request ready by the GitHub MCP update tool (draft false) when `merge <pr> --ready` has not passed its ready checks on that pull request's current head? Ruling: no. Guard rule `ready-mcp-mark-guard` refuses the mark (roadmap step `ready-mcp-mark-guard`, from coordinator 05:50 CST Nov 15, relayed).

- The rule reads the session's own transcript for a Bash or PowerShell call with `--ready` or `--confirm` (never `--fast-checks`, which builds no records page). `merge/merge.py` prints the lines the rule reads from its `READY_*_FMT` templates, and the guard builds its patterns from the same templates (`ready_line_pattern`), so no copy of a line sits in the guard. The reader is `lint/_transcript.py`, the one home of transcript reads.
- A run stands for a head in three forms. The pass line `merge: the ready checks (...) pass on <sha>.` names it. On a base that is not the default, the pass is on a dry merge commit, so the line `merge: the dry merge of <head> into <base> is <dry>.` maps a pass on `<dry>` to `<head>`. In a repo with no `merge.readyChecks` there is no pass line, so the run stands for the head that a line of the draft step names (records page current, records page pushed, base merged, a Record-claim stop, or on a base that is not the default, `merge: the draft step ran no checks on #<n> at <sha>.`), and only after the run's no-checks line.
- The pass counts only when its sha is a prefix of the head the pull request has now (`Host.pr`). A pass on an older head, and a run that stood for no head, are refused. A `#12` selector reads as `12`, as in rule records-page-ready.
- The refusal names `merge <pr> --ready` as the remedy and never names the mark it refuses (rule `git-remedy-never-names-target`).
- Judged only in a repo that uses the merge tool. An update with draft true, a body-only update, a missing or unreadable transcript, and a head that cannot be read pass this rule. The records-page-ready rule reads the same head first and refuses an unreadable one (decision `records-index-at-merge`).
- Scope: the MCP update tool only. The `gh pr ready` form is not read here (debt `pr-ready-unguarded`). In a cloud session a `gh` write is already refused (rule `gh-write-cloud`).

## Incident, risk and cost

Incident: PR 3255 (04:25 CST) and PR 3472 (05:40 CST), 2026-11-15. Each was marked ready by MCP, which skips the records step of `merge <pr> --ready`. Each then met a stale records page at the confirm, and the confirm refused it. Risk kind: named incident. Harm: one extra CI cycle per mark (decision `records-index-at-merge`: one full `checks` run took 44 min, n=1) and a ready PR whose head changed after its ready run.

Open risk: `--ready`'s own mark is refused by GraphQL, so the session marks ready by MCP after the pass (decision `records-index-at-merge`, the ready route). That mark follows a pass on the same head, so the rule allows it. A session that ran `--ready` in another session, or before a compaction, meets the refusal and runs `--ready` again. Unmeasured: how often.

Cost: only an update with draft false reads anything. It makes at most one transcript read (the whole file) and at most one pull request read, the second only when a stood sha is found. No process outlives the call and no file is written.

Debt: `ready-checks-skipped-by-mcp` retires on a guard case that shows a ready mark outside the draft step is refused. Family `ready-mcp-mark-guard` in `hooks/test_guard.py` is that case.

Kind: build
Plan: docs/decisions/ready-mcp-mark-guard.md#the-ruling (all)
Home: hooks/guard_merge.py
