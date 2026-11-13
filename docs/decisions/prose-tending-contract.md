# Every prose store is tended by one shared contract and one runner

## Ruling

Owner, 2026-11-11 10:19 CST: "everything that marks prose should share the same 'tending' mechanism ... more
uniform, standardized, and shared as much as possible". Each prose store (decisions, rules, docs, debts,
handoffs, the feedback log, the roadmap and queue, the copies of pages, the mailbox) names in
`lint/layout.json`, key `tending`: its item shape, one "still true?" test and one close step. One runner,
`lint/tending.py`, applies it. It is called only from points that already run: the merge check, the Stop
hooks, compaction and triage status. It starts no timer, watcher or process. A store is `declared` until a
call point runs it, then `live`.

Owner, 2026-11-12 12:30 CST, on "a token never goes in a page" (a separate ruling on the waiting page): "not
sure i agree ... keep your options open". This record builds on no such line and removes none.

Lane rulings on the runner's verdicts (lane prose-tending-contract, 2026-11-12 13:42 CST, from review round 1).
This was the lane's own call, open to the owner. A live store whose file is missing fails the merge check.
A file that cannot be read is reported as `unknown`, never as clear or broken. So is a line whose shape is
not read. Neither fails the merge check. The merge check writes nothing. A stale line is closed only at the
Stop, compaction and triage-status points. A close marks the stale line, never every line sharing an id.

Kind: build
Plan: docs/plans/prose-tending-contract.md#contract-lintlayoutjson-key-tending (claude-settings)
Home: lint/tending.py
