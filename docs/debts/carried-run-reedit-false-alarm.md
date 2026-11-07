# The carried-run check refuses a file that the lane and main both edited, when main edits it again

**What.** A lane and main make the same edit to a guard or check file. The lane's record is carried to a later head. Then main edits that file again, and the lane merges main. The carried-run check sees a change to the file after the reviewed head that the merge-base cancel-out does not remove, so it refuses (`--review-record`) or reads `open` (`--reviewed`). No reviewer owes that read, since main's own change came in. The lane must write a new Round line or a Fix check.

**Where.** `merge/merge.py`: `unreviewed_guard_paths`, which merges the first head with the merge base of the new head and `origin/<base>`, and `carried_refusal`.

**Decision.** `pr-review-record` (the review record and its carried-run check), the limits section.

**Retire.** Make the check tell main's later edit from the lane's own work, for example by diffing against the base's merge result instead of the merge base. The check: a case in `merge/test_merge.py` makes the same edit in the lane and on main, has main edit the file again, merges main into the lane, and reads `--reviewed` as done.
