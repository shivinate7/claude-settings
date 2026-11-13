# A question on another repo is checked with that repo

## The ruling

An open decision or task on a repo's waiting page names the repo it is about. A question about another repo is checked with a session of that repo before it reaches this page's owner.

- Every open decision and task carries `repo` (`owner/name`). The compare folds case.
- A `repo` other than the page's own repo needs `checked_with`: the session id of that repo's triage, coordinator or owner's-computer session that said the owner has not ruled on it.
- A `checked_with` that equals the session id in the item's `owner`, or the record id of the cloud session that writes the item, is refused. The session that files the item did not check.
- Guard rule `question-checked-with-repo` (`hooks/question_form.py`, `cross_repo_hit`, called by `item_hit`) refuses a `set` of an open decision or task that breaks the lines above. It refuses an `update` that carries `repo` and breaks them. It refuses an `update` that carries `checked_with` with no `repo`. A `repo` that is not `owner/name` (a `.git` suffix, a URL, a bare name) gets a format reason that names the page's own repo as the example.
  - The open filter is `_open_decision`, the one home of the page's decision rules: a missing kind is a decision, and any status but `closed` is open. The writer's session id is the cloud session's record id: `hooks/guard.py` and `hooks/call_judge.py` pass `override.remote_session_id()` (env `CLAUDE_CODE_REMOTE_SESSION_ID`, `cse_<x>` read as `session_<x>`). The hook payload's `session_id` is a local UUID, never a record id. A local session has no record id, so the writer-session check is cloud-only; the `owner` check runs everywhere.
  - It keys on fields, never on words (rule `predicate-is-the-act`, in `docs/decisions/an-agent-outside-its-home-tree-must-stop.md`).
  - The page's repo is the origin of the checkout the write is judged at (`lint/layout.py`, `repo_name`). `cross_repo_hit` requires `repo` even when the page's repo is unknown, but `item_hit` calls it only when the page's repo is known: with no origin, or no checkout, the write passes.
  - A `str_replace` on `repo` or `checked_with` is refused: it changes the verdict and the guard cannot see the stored item. Send an `update` that carries both. This refusal fires even when the page's repo is unknown. An `update` that carries `checked_with` with no `repo` is refused for the same reason, but only when the page's repo is known. A closed item and an `update` with neither field pass; whether an `update` can create a document is unverified.
  - Both fields are in the `itemFields` block of `skills/waiting-page/page.html`, the one list the page and the guard read.
  - The session id shape is `own_session._CREATED_ID` and the repo shape is `stale_pages.REPO_NAME`, both imported. `cross_repo_hit` narrows `REPO_NAME` at this one caller: it also refuses a `repo` that ends in `.git`, which `REPO_NAME` accepts.
  - Repo config reads (`repo_keys`, `waiting_page`) read `.claude/layout-extras.json` from `origin/HEAD`'s branch, else `origin/main` (`lint/layout.py`, `_default_branch_extras`, `_config_source`). The blob wins whole. The checkout's file is used only when no blob resolves: no origin, no ref, a git error, a timeout, or a blob that does not parse (same parser). A checkout file that does not parse raises `LayoutError` before any blob read. The read touches refs only: no checkout moves, no fetch runs. A source with no page gives "unknown".
  - The read has a wider effect: `lint/report_guard.py`, `hooks/feedback_guard.py` and `lint/compliance_probes.py` also read the page through `waiting_page`, so they see the blob's page on every checkout that is not a fork.
  - Cost of that read: at most one `git cat-file --batch` process per call (pinned by `lint/test_layout.py`), on every checkout that is not a fork, 10 seconds, no file written.
  - A fork (its file sets "record-branch") keeps its own file whole: 0 starts.
  - The rolled-out check (`rolled_out`), the writers (`set_waiting_page`) and the colour and icon reads (`waiting_page_colour`, `waiting_page_icon`) read the checkout's file only.
  - Part (a) of ledger row D14 (session checkouts go stale), reversing step grants-read-from-main (a session reads standing grants from origin/main), waits on the owner.
  - The reason names the field. For a missing `repo` it names the page's own repo as the value to write, so one retry fixes it.

## The mistake and the harm

The mistake: triage filed another repo's design questions on this repo's page. The owner had already ruled on them. The harm: the owner answers a question twice, and the second answer can contradict the first.

Incident: mailaudit item `ma144-tab-bar` (mailaudit #144, the Duo tab bar place), filed on this page by a batch runner session. The owner's ruling on the Card in Hand design already covered it.

Second incident: item 397, 2026-11-07 22:58 CST. Triage writes the page from a worktree on the record branch. That worktree holds no extras file, so the page read as unknown, no page check ran, and every rule above was skipped.

Cost of the field check: no process, no file written, except the default-branch read above. One read of git's config file per waiting-page write (`lint/layout.py`, `repo_name`) (unmeasured).

Known limit: the guard sees that `checked_with` is session-shaped, not that the session checked. A made-up id passes. Review and the owner catch it.

Kind: process
Home: rule:questions-go-to-owner
Landed 2026-11-08.
