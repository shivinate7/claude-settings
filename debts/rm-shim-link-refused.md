# A recursive rm of a symlink is judged by its target

- **What.** `bin/rm` resolves each operand before it judges it. `rm -r link`, where `link` points at home, the cwd or a parent of the cwd, is refused. The real `rm` removes only the link.
- **Where.** `bin/rm`, the operand check.
- **Decision.** `rm-path-wrapper` (a PATH shim refuses a recursive rm of a critical folder).
- **Retire.** Judge a symlink operand with no trailing slash as the link itself, with a test case.
