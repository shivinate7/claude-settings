# The --confirm preview reads the carried head

- **What.** The `--confirm` preview's records line reads only the carried head. For a green live head it says "--confirm refuses it", but no gate reads that text, and confirm merges.
- **Where.** `merge/merge.py` lines 5264-5270.
- **Decision.** `merge-needs-current-base` (the carried proof of a stale records page, and the live head's own run).
- **Retire.** The preview reads the live head as confirm does. Check: `merge/test_merge.py`.
