# install.sh retries the final rename like install.ps1

## The ruling

`put_file` in `install.sh` renames `DEST.cs-new` over `DEST` with up to 25 attempts, 0.1 s apart (about 2.4 s), the budget of `Move-OverFile` in `install.ps1`. After the last attempt it prints the stderr of that `mv`, then "could not replace", and sets `INSTALL_FAILED`.

Why: a rename held up by an open reader is retried briefly (`install-hooks-whole`, an install never shows a session a half-copied hook). A single `mv -f` failed with "Device or resource busy" on Windows CI.

Kind: process
Home: install.sh
