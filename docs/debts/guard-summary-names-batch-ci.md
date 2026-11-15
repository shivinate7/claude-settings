# The guard's merge-checks summary names a batch CI refusal

**What.** The `merge-checks` summary in `hooks/guard.py` (about lines 151 to 152) says a merge is denied "while another ready PR on the base runs CI". The per-lane guard does not hold a merge for another ready PR (`hooks/guard_merge.py`, header line 37). The summary describes a refusal that is gone.

**Where.** `hooks/guard.py`, the `merge-checks` summary (about lines 151 to 152).

**Decision.** none

**Retire.** Reword the summary to the refusals the guard still makes: a pending or red check on the head, or a check that could not be read. Check: a case in `hooks/test_guard.py` that reads the summary and finds no "another ready PR". Red on the current text, green after the fix.
