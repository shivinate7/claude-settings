# install.sh retries the final rename like install.ps1

Kind: process
Home: install.sh

`put_file` in `install.sh` renames `DEST.cs-new` over `DEST`. It now retries the rename 25 times,
0.1 s apart. This is the budget of `Move-OverFile` in `install.ps1`. After the last try it prints
"could not replace" and sets `INSTALL_FAILED`. It also prints the stderr of the last `mv`.

MEASURED, CI history: the Windows test `swap1sh` (`hooks/test_install_src.sh`) failed in 3 of 24
runs (12.5%). The error was `mv: cannot move '...guard.py.cs-new' to '...hooks/guard.py': Device or
resource busy`. A running `python3 guard.py` holds the file open. Windows refuses a rename over an
open file. The old code ran `mv -f` once. Unmeasured: the failure rate after the retry. CI settles it.

Governing record: `install-hooks-whole` (an install never shows a session a half-copied hook). It
says a rename held up by an open reader is retried briefly.

## Holes, named

None. The `mv` shim in `hooks/test_install_src.sh` may pause twice when the real `mv` fails and is
retried. A test-author owns that edit.
