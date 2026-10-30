# Step scan knows only a list of programs

- **What.** Guard rule `command-in-item` reads a backtick span in a step as a shell line only when its first word is in a fixed program list. `gsutil ls`, `yarn install`, `kubectl get`, `terraform plan`, `chmod +x f` and `grep -r x` pass.
- **Where.** `SHELL_PROGRAMS` and `_shell_line` in `hooks/guard.py`.
- **Decision.** `act-in-place` (the owner acts where he reads).
- **Retire.** Also count a span whose second word is a flag (`-x` or `--x`), and add the cloud CLIs this session uses. Tests for the six spans above are red on the old code and green on the new.
