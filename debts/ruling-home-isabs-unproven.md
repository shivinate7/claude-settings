# No test proves the absolute-path refusal in ruling_home

- **What.** `value_resolves` refuses each absolute `home:` value. On Windows, a mutant without that refusal leaves every absolute row green. The git lookup refuses the same value. Nobody measured this on Linux. The refusal may be redundant, or a row may be missing.
- **Where.** `value_resolves` in `hooks/ruling_home.py`; `hooks/test_ruling_home.py`.
- **Decision.** `test-strategy-reset` (each kept test names the real failure it catches).
- **Retire.** With the refusal removed, one row goes red on Linux and Windows. Or the refusal goes as redundant, with a measure on both platforms.
