# The ruling-skip roadmap read never fetches

**What.** The ruling-skip check reads the owner's waiting-page items from the local roadmap ref, and that read never fetches. On 2026-11-06 a cloud clone with tip 13:13 CST lacked waiting-page item 289, answered at 13:59 CST. A true cite then refused "item 289 is not on the roadmap branch". The refusal's remedy never says to fetch the roadmap branch.

**Where.** `lint/report_guard.py`, `_read_roadmap_answers` and `_ruling_of_item` (the "is not on the roadmap branch" text). Both read through `hooks/question_form.py`, `read_json_folder`, whose docstring says "Never fetches".

**Decision.** `questions-go-to-owner`, questions go to the owner (its ruling-skip bullet: an item is read from the roadmap branch).

**Retire.** Closed when a case in `lint/test_report_guard_ruling_skip.py` cites an item that a stale local roadmap ref lacks, and passes. The case goes red first. The fix is a fetch, which adds a network read to the Stop run and changes the decision's cost line, or a remedy that names the fetch.
