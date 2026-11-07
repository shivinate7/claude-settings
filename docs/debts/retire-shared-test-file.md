# A Retire names a shared test file

- **What.** The birth-commit run of decision `debt-close-runs-retire` runs a whole test file, not the test the Retire names. A shared file can fail on an old birth commit for reasons unrelated to the debt, so the close passes whatever the named test does. Five debts' Retire lines name `hooks/test_guard.py`.
- **Where.** `lint/check_debt_retire.py`, the birth-commit run. It runs the whole named file as one argv.
- **Decision.** `debt-close-runs-retire`, the birth-commit run it sets. The remedy follows decision `uniform-over-variants`: no second span form.
- **Retire.** Prose. No runnable check proves it yet. The finding closes after every debt that names a shared test file names a test file of its own.
