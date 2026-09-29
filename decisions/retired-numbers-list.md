# A retired number leaves through a list

On 2026-09-29 the owner ruled: "Allow delete, keep a list". In q_max, D-570, "A decision
that no longer governs is deleted", makes deletion the way a record retires. The stamp
refused each delete, because numbers are permanent.

## The ruling

- A record may be deleted when its number is named in the kind's `RETIRED` file, in the
  same tree. One line for each number: the id, then optionally its last title.
- The list is append-only. A number the base list names must stay named.
- The allocator counts a listed number as taken. It never hands one out again.
- The heading format does not read the list. A removal there stays refused.

## What this protects

The refusal exists so that no number is given out twice. The allocator takes the highest
held number plus one, so a deleted top number could return. The list holds the number after
the record is gone. Each rule has a test that goes red on its own defect, in
`actions/stamp/test_stamp.mjs`.

## What would reopen this

- A repo that uses the heading format needs to delete records.
- A listed number is given out again. Bring the case to the owner.
