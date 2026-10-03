# The Windows launcher bin/verdict.cmd has no test

**What waits.** `lint/test_verdict.py` runs `bin/verdict` through Python on every OS. Nothing
runs `bin/verdict.cmd`, so the Windows launcher is proven by reading only.

**Why it waits.** It has the same shape as `bin/merge.cmd`, and no failure is known. A reviewer
found the gap while checking integration batch 1 on 2026-10-02.

**What keeps it from being lost.** This file.

**Trigger.** When `bin/verdict.cmd` or `bin/merge.cmd` next changes, add one gates-windows case.
It runs `bin\verdict.cmd` on a passing and a failing command, and checks the exit code.
