# claude-sharables claims ids with its own tool, not the stamp

**What.** claude-sharables claims record ids with its own `scripts/check_records.py --claim-ids --apply`. The `merge` tool claims through the shared stamp and stops without `.github/stamp.json`, so it cannot run there. Unmeasured: whether the stamp can write sharables' ids, which have no hyphen and no padding (`D93`).

**Where.** `actions/stamp`, and claude-sharables.

**Decision.** `one-shared-record-stamp`, one shared parser, not four claim tools.

**Retire.** Move sharables onto the stamp. If the stamp cannot write its ids, change the stamp here first. Revisit at sharables' next claim of a record id, or the next stamp change. Closed when the `merge` tool runs in sharables.

## Ruling

Owner, 2026-10-06: sharables moves its claim onto the stamp. The `merge` tool gets no setting that names a repo's own claim command.
