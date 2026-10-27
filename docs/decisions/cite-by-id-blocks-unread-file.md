# cite-by-id blocks a message file the guard cannot read

## The ruling

Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): the guard blocks `git commit -F <file>` when it cannot read the file at hook time. The cost is one retry with `-m`.

Reason: a message file may cite a record by its path. The same command often writes the file, so the guard cannot read it yet, cannot check the cite, and an allow would let that cite through.

Kind: process
Home: rule:git-cite-by-id
Home: hooks/guard.py
