# An unknown flag to the guard mutation test starts the full run

- **What.** `python3 hooks/mutate_guard.py --help`, or any flag that `main` does not know, falls through to the full mutant run: every mutant and every control, which holds the machine for many minutes. A builder in lane mutate-guard-split ran `--help` to read the usage and had to stop the run.
- **Where.** `main` in `hooks/mutate_guard.py`.
- **Retire.** `main` refuses an unknown flag with a usage line and exit 2 before any suite runs, with a case in `hooks/test_mutate_shared.py` that goes red on the old code.
