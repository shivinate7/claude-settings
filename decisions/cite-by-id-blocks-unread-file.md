# cite-by-id blocks a message file the guard cannot read

## The question

May the guard allow `git commit -F <file>` when it cannot read the file at hook time?

## The ruling

Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): keep the block. The same command often
writes the file, so the guard cannot read it yet. The cost is one retry with `-m`.

## The reason

A message file may cite a record by its path. The guard cannot read the file, so it cannot
check the cite. An allow would let that cite through.

## What protects it

`hooks/test_guard.py`, the cite-by-id block dated 2026-10-17. It denies a missing message file.
It pins three cases as denied. A file that a redirect writes in the same command is one. A file
that a heredoc writes in the same command is another. A message made by a process substitution
is the third.

Kind: process
Home: rule:git-cite-by-id
Home: hooks/guard.py
