# The Unstarted shared-file check lets one bullet's file cover the others

- **What.** The Unstarted shared-file check joins every bullet under one bare `Unstarted:` line into one item. One bullet that names a shared file then passes every other bullet in that item, including a bullet that waits on a merge or PR and names no file. The decision says each bullet is its own item.
- **Where.** The defect is live on main at `lint/report_guard.py:1099-1163`: `_unstarted_item` joins the bullets, and `_names_a_file` tests the joined text. `unstarted_problem` calls both. The code came with PR #3684 (the Unstarted shared-file check), merged. Rule `reports-name-unstarted-items` (a report names each unstarted item) is the rule it enforces.
- **Decision.** `guard-remedy-not-to-owner`, a Stop refusal's steps live in its record, not in chat. Its shared-file section, on main at `docs/decisions/guard-remedy-not-to-owner.md:50-62`, says each bullet is its own item.
- **Retire.** Closed when the check tests each bullet on its own, so a bullet with no file is refused even when a sibling bullet names one, and `lint/test_report_guard.py` holds that case and it passes.
