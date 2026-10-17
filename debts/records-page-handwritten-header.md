# The records-page guard reads a hand-written page as generated

- **What.** The guard `records-page` acts only when the base page opens with `# Records index`. A hand-written page that opens with that line reads as generated. A lane commit that changes it is then refused.
- **Where.** `hooks/guard_merge.py`, `records_page_hit`: the `opens.stdout.startswith(RECORDS_HEADER)` test.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** The generator writes a marker line, such as an HTML comment, that no hand-written page copies. The guard reads that line in place of the title. A case in `hooks/test_guard.py`: a hand-written page that opens `# Records index` and lacks the marker is no hit. It shows red on the current code and green after the fix. The pin test for the header copy (`test_the_guards_records_header_opens_the_generated_intro` in `lint/test_hook_catalog.py`) then follows the marker.
