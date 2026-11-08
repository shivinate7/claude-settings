# Guard data files are off the guard path list

**What.** Two guards read their verdict from data files outside `GUARD_PATHS`. The `itemFields` block of `skills/waiting-page/page.html` is the allow list of the waiting-page item check (`hooks/question_form.py`); an unreadable block passes every item write. The Commands table of `skills/impeccable/SKILL.md` decides the impeccable chain refusal (`hooks/guard.py`). `merge --review-record` derives only `hooks/guard.py`'s import closure (`merge/merge.py` `guard_import_closure`), so a mistaken edit to either file passes Guard or check `no` and skips the net-value test. Reachable in normal work: lanes edit the page often. Found in review round 1 of lane lint-config-guard-paths.

**Where.** `merge/merge.py` `guard_hits`; the two data files above.

**Decision.** pr-review-record.

**Retire.** Count a change to the guarded part only. Parse the `itemFields` block and the Commands table in the PR diff, so that an edit elsewhere in the page is no guard change. The check: a `merge/test_merge.py` case where a PR that edits only the `itemFields` block with Guard `no` is refused, and one that edits only page styles is not.
