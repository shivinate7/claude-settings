# Mutant file names must differ on a case-insensitive filesystem

## The ruling

- `safe_name` in `hooks/mutate_shared.py` appends a short digest of the exact label, case included. The digest does not depend on the label's position in `MUTATIONS`.
- `main` in `hooks/mutate_guard.py` refuses to start, before any suite runs, when two mutants would still share one path on a case-insensitive filesystem.

Why: two labels that differ only by one letter's case (`branch-delete: -D` and `-d`) shared one copy file on Windows. The mutants raced, and one got a WRONG CAUSE verdict. The mutation itself was correct. The cause was the shared file name, not the platform.

Kind: process
Home: hooks/mutate_shared.py
