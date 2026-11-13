# The tsc lookup misses a Windows shim

**What.** `loadTypescript` looks for `tsc` with no file extension on each PATH folder. An npm install on Windows writes `tsc.cmd` and `tsc.ps1` shims, so the lookup may find nothing. A builder's comment-only edit to a JS or TS test file then refuses on Windows, as `comment_only_change` fails closed. Claude could meet this in normal work on Windows. Harm: a comment-only test edit that the owner allowed is refused there.

**Where.** `lint/typescript_on_path.mjs` (`loadTypescript`), used by `hooks/comment_only.mjs` and `lint/comment_scan.mjs`.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests.

**Retire.** `loadTypescript` also tries `tsc.cmd` and finds the package behind it. Closed when `lint/test_typescript_on_path.py` has a case with only a `tsc.cmd` shim on PATH that loads the package, and the case passes.
