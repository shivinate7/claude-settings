# A lane can claim a merge role

**What.** `write_merge_role` checks only that the tier is in MERGE_ROLES. Nothing ties it to the session's own `cs-build:<tier>` tag. A lane that misreads its tier can run `merge --role coordinator`, and with the cloud allow rule, nothing asks. No cheap tie exists: the tier line in `hooks/session_start.sh` never learns the tier, because get_session is an MCP tool only. A fix needs a sessions API call from `merge.py` or from a hook.

**Where.** `merge/merge.py`, `write_merge_role`; `merge/cloud_allow.json`.

**Decision.** `session-tiers` (the session tiers; bullet "Merge role").

**Retire.** Read the session's own `cs-build:<tier>` tag, and refuse a `--role` that names another tier. Check: a fixture test where a lane tag runs `--role coordinator`. It is refused. Red on the current code, green after the fix.
