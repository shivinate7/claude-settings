# A write into the pointer checkout is refused

## The ruling

The guard refuses a Write, Edit, MultiEdit or NotebookEdit whose target is one of the pointer checkout's own
files. The pointer checkout is the one checkout the owner's global rules file names. Every session on this
machine runs its hooks, lint and agents out of it, so an edit there is live for all of them before any review.

- **The mistake.** The lane `fresh-round3-route` (a lane is one unit of work, named by its branch slug) edited
  the pointer checkout. It merged in PR 2411 on 2026-11-09 at 12:10 CST. The `pointer-head` rule (refuses a
  move of HEAD off `main` in the pointer checkout) refused only the branch switch, not the edit.
- **The harm.** The edit lands in a checkout that every session reads, before review.
- **The rule.** A Write, Edit, MultiEdit or NotebookEdit onto one of the pointer checkout's own files is
  refused. The reason names the EnterWorktree tool as the remedy.
  - Passes: the pointer's own `.git`; a linked worktree, under `.claude/worktrees/` or elsewhere; a target
    outside the pointer; an unreadable or missing pointer; Read and Grep. Artifact and ArtifactData are not
    writes and pass.
  - A shell write is not judged.
- **Liftability.** An owner override (the `owner-override` decision, the owner's typed override) lifts a direct
  pointer path while the pointer is a plain checkout. Two cases lift nothing:
  - The pointer is the live pinned checkout or the main mirror. `is_frozen` then covers every file in it, and
    the `frozen-path` rule (refuses writes to frozen files and checkouts) already refuses them. The
    `never_lifted` list reads `is_frozen`, so no override lifts them.
  - A config-dir spelling that resolves into a frozen directory. The same reason applies.
- **Value.** Reviewer round 3 judged the net safety value small and positive (the `hold-unsafe-after-round-3`
  decision, the net-value test).
  - Safety holes closed: a session whose cwd is in the pointer checkout; a session in another repo, or with no
    checkout, writing a pointer path; a non-isolated agent writing a pointer path.
  - Safety holes opened: none.
  - It adds value only while the pointer is a plain checkout, such as a cloud session's own checkout or a local
    install before its first merge. `frozen-path` covers the steady state.
- **What protects it now.** The `pointer-edit` family in `hooks/test_guard.py` (19 cases) and four
  `pointer-edit` mutants in `hooks/mutate_guard.py`. No case tests an override against it. Its gaps are the
  notes in `docs/debts/notes.md` that cite this decision.

Risk kind: incident, per the `building-guard-needs-incident` rule (a guard is built against a mistake Claude
has made): PR 2411, 2026-11-09 12:10 CST.

Cost, per the `outcomes-mechanize-rules` rule (cost stated in the record): each Write, Edit, MultiEdit and
NotebookEdit call reads the global rules file once (at most 64 KiB) and resolves its target paths. It starts no
process and runs no git. A refusal adds one line to `guard.log` (unmeasured).

Kind: build
Plan: docs/decisions/pointer-edit.md#the-ruling (all)
