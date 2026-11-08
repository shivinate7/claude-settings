# A done-check label then a blank line reads as an empty done check

- **What.** Rule `builder-brief-code-check` ends a done-check section at the first blank line or `#` line. So `**Done check:**`, a blank line, then a bullet that runs `merge --lane-lint` is refused, and so is a fenced done check that holds a blank line or a `# comment`. The refusal asks the writer to add what is there. A fix on PR #2192 (commit c4971f2e1, reverted) failed its fix check: an unclosed fence, or a fence opened on the label line, let a later paragraph count as the done check.
- **Where.** `_builder_done_text` and `BUILDER_SECTION_END` in `hooks/guard.py`.
- **Decision.** `builder-brief-code-check` (a builder's done check runs the checks job's lint).
- **Retire.** Skip blank lines right after a bare label, and read a closed fence whole. An unclosed fence, or a fence opened on the label line, must still end at the first blank line. The `builder-code-check:` cases in `hooks/test_guard.py` pass, with allow cases for each form above and deny cases for both fence bypasses.
