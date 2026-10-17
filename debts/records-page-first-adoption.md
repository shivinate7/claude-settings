# The records-page guard lets a first page pass

- **What.** When the base has no `docs/records.md`, the guard `records-page` allows any lane commit of the page. This is by design: a first adoption has no base page to compare with.
- **Where.** `hooks/guard_merge.py`, `records_page_hit`: the `not base_id` test (a base with no page) skips the judge.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** The owner rules how a first page lands. If it must come from the merge tool, the guard refuses a page on a base with none. A case in `hooks/test_guard.py` pins the refusal. If not, the limit stays by design. Then delete this debt and rewrite the decision entry in place.
