# Outbox: c124 build thread

- c124 (lint tests share one folder-removal helper): merged in batch #698 (43d9af2) via PR #695. Ready to close.
- Note, not a debt: testing/tracked_tree.clear_readonly sets mode S_IWRITE only, so a read-only directory passed to it would lose read and execute bits on POSIX. No fixture holds a read-only directory today (review round 2, c124).
