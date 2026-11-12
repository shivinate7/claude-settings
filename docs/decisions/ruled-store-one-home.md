# An owner ruling not yet on main lives in one store, read by one module

## The ruling

The owner's rulings that main has not taken in sit in one store: `roadmap/rulings/<slug>.json` on `origin/roadmap`, one file per ruling. `lint/ruled_store.py` is the only reader. The session-start hook (`hooks/session_start.sh`) prints the open entries once, and the question judge's past-ruling search (`past_rulings` in `hooks/question_form.py`) lists them first as `ruled:<id>`. An entry closes when its `status` is `closed`, or when the text in its `lands_in` is found on `origin/main` at the path it names. Triage writes the entries, and the restart plan (`docs/plans/restart-plan.md`) cites an entry by id and does not copy the ruling. The switch `ENTRIES_LIFT_GUARDS` in `lint/ruled_store.py` is False (owner, waiting-page item 646, option a): an entry is text only and lifts no guard rule. Setting it True lets an open entry lift the guard rules it names. Nothing calls that function yet.

Protected by `lint/test_ruled_store.py` (the reader, the close rule, the switch, the session lines, two git starts for one read), `hooks/test_session_start.py` (the hook prints the block, and prints nothing when no entry is open) and `hooks/test_question_form.py` (the entry is the first candidate, a closed one is none, an absent store is only an unknown source). `python3 lint/ruled_store.py check REPO` exits 1 on an entry that lacks `id`, `at`, `ruling` or `source`, has an `at` with no zone, or has neither `supersedes` nor `supersedes_none`.

Cost: the hook starts one python and up to three read-only git processes per session start, with no fetch, file or timer of its own.

This record is dated by one fact: the store lives on `origin/roadmap`. If the entries move to main, rewrite the record.

Kind: build
Plan: docs/decisions/ruled-store-one-home.md#the-ruling (all)
Home: lint/ruled_store.py
