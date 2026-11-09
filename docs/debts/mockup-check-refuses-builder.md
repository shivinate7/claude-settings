# A Mockup set check refuses the next builder

**What.** The design-review skill's Mockup set check spawns one design reviewer before any builder. That spawn counts as a reviewer round, so the next builder spawn is refused for a missing review record, though no round exists to record. A design lane hits this in normal work.

**Where.** `hooks/guard_merge.py`, rule `review_record_hit`: every reviewer spawn (`RECORD_REVIEWER_ROLES`) anchors a round. The spawn comes from `skills/design-review/SKILL.md`, its Mockup set check, step 1.

**Decision.** pr-review-record (a pull request carries its review record on the PR).

**Retire.** A builder spawn after a Mockup set check is not refused for a review record. A case in `hooks/test_guard.py` shows it: a design-reviewer spawn with a Mockup set brief, then a builder spawn, and no refusal.
