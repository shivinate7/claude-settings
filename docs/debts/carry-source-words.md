# Carry source words are too few

**What.** `SOURCE_RE` accepts only the words git, page and digest as the source of a Recovered item. The guard refuses an item that names its source another way, such as "commit abc1234", "GitHub PR" or a github.com URL. Claude is likely to write those forms. Each one costs one refusal per compaction.

**Where.** `lint/report_guard.py`: `SOURCE_RE`, used by `unsourced_recovered_item`.

**Decision.** precompact-handoff (checkpoints keep the handoff current). Its item 11 names git, page and digest as the only sources.

**Retire.** Closed when a case in `lint/test_report_guard.py` passes a Recovered item that names a commit, a GitHub PR or a github.com URL. A second case still refuses an item with no source.
