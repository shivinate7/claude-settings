# A script file run by name can write a test

**What.** A heredoc writes a script to a file, such as `cat > /tmp/gen.py <<EOF`. A later `python3 /tmp/gen.py` then writes a test file. The shell check reads the heredoc as a write to a non-test path, and the run as a command with no body, so the guard allows it. The 2026-11-01 incident session ran this shape, so the gap is likely.

**Where.** `hooks/guard.py`, `builder_shell_test_hit` (rule 7c, `builder-test-edit`). It reads a heredoc body and a `-c` or `-e` script. It does not read a script file that a command runs by name.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the shell check).

**Retire.** Read the script file a command runs, or the file a heredoc in the same command writes, and judge its writes. Closed when a red case in `hooks/test_guard.py` writes a test path this way and the guard refuses it.
