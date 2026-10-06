# claude-sharables adopts the stamp, not a claim-command setting

**What waits.** claude-sharables claims record ids with its own
`scripts/check_records.py --claim-ids --apply`. The `merge` tool claims through the shared stamp
(`actions/stamp`) and stops without `.github/stamp.json`. So `merge` cannot run there, and its
local main is not moved after a merge.

**Ruling, owner, 2026-10-06.** sharables moves its claim onto the stamp. The `merge` tool gets no
setting that names a repo's own claim command. This follows `one-shared-record-stamp`, one shared
parser, not four claim tools.

**Why it waits.** The work is in sharables, not here. Unmeasured: whether the stamp can write
sharables' ids, which have no hyphen and no padding (`D93`). If it cannot, that is a stamp change
here first.

**Trigger that brings it back.** The next sharables session that claims a record id, or the next
stamp change here.

**Owner.** The sharables orchestrator that moves sharables onto the stamp.
