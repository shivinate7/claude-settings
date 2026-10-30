# A lane can claim a merge role

**What.** `write_merge_role` checks only that the tier is in MERGE_ROLES, not the session's own `cs-build:<tier>` tag. A lane that misreads its tier can run `merge --role coordinator`, and with the cloud allow rule nothing asks (misread rate unmeasured).

**Where.** `merge/merge.py`, `write_merge_role`; `merge/cloud_allow.json`.

**Decision.** `session-tiers` (the session tiers; bullet "Merge role").

**Retire.** Read the session's own `cs-build:<tier>` tag, and refuse a `--role` that names another tier. This needs a sessions API call from `merge.py` or from a hook: the tier line in `hooks/session_start.sh` never learns the tier, because get_session is an MCP tool only. Check: a fixture test where a lane tag runs `--role coordinator`. It is refused. Red on the current code, green after the fix.
