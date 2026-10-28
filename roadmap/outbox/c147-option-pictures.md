# c147-option-pictures (each design option's picture shows its own difference)

State: green, reviewed, handed to the orchestrator. Draft PR #753, head 0b3ad80f.
- `problem()` in the waiting page blocks Send when two options show the same picture (same slug or same bytes) with the same focus, or when a design's focus finds no element.
- Red first: 3 new tests went red on the old page (today's case: A and B share one slug). Suite 121/0 after the fix.
- Gates: ci-job gates --lint PASS, ste-changed PASS, silent-undo clean.
- Review round 1 (Sonnet): APPROVE. Notes, none blocking:
  - The check runs on non-look decisions too.
  - The focus compare is a string compare, so `#row` and `.row` on one element pass.
  - Each problem() call parses each focused mockup again. The cost is unmeasured; a cache keyed by slug and focus would remove it.
