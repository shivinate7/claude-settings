# install.sh retries the final rename like install.ps1

Kind: process
Home: install.sh

`put_file` in `install.sh` renames `DEST.cs-new` over `DEST`. It now makes up to 25 attempts, 0.1 s
apart, so a failure costs about 2.4 s. This is the budget of `Move-OverFile` in `install.ps1`. After
the last attempt it prints the stderr of that `mv`, then "could not replace", and sets
`INSTALL_FAILED`.

MEASURED, CI history (Explore run, `gh api` job logs, 2026-10-17): the Windows test `swap1sh`
(`hooks/test_install_src.sh`) failed in 3 of 24 runs (12.5%). Each failure was `mv: cannot move
'...guard.py.cs-new' to '...hooks/guard.py': Device or resource busy`. The old code ran `mv -f` once.
Unmeasured: which process held the file. The test runs `python3 guard.py` in a loop during the
install, so a running guard is the likely holder. Unmeasured: the failure rate after the retry.

Governing record: `install-hooks-whole` (an install never shows a session a half-copied hook). It
says a rename held up by an open reader is retried briefly.

The test shim `make_swap_bin` now pauses only once. It matters only for an injected failure: a
failed and retried `mv` at the pause point would pause twice, and swap1sh would fail. A normal run
does not change, because the CI failure was at a later file. The test-author showed it red with a
forced failed `mv`, then green.

## Holes, named

1. `install.sh` retries every `mv` error. `install.ps1` retries only Win32 codes 5 and 32. A
   permission or missing-path failure now takes about 2.4 s per file before it fails. Orchestrator's
   call: a failed install already fails, and sh cannot read the error code. Debt:
   `install-sh-retries-every-error`, the sh retry does not filter by error.
2. Five other renames have no retry. The cloud `settings.json` swap is the same class as
   `put_file`. Debt: `install-sh-renames-no-retry`, five install renames are tried once.
3. No test drives the retry success path or the exhaustion path. Debt: `install-sh-retry-untested`,
   the mv retry has no test.
