# The test hook reader can still die with no output

- **What.** `HookReader` counts each read fault, but two lines sit outside its try: the file-name read and the body index. A throw there ends the test process with no output. Its comment says it never dies.
- **Where.** `install-no-gap.test.ps1`, `HookReader`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** The whole reader loop body is inside the try, and the comment is true.
