# A Retire names a shared test file

- **What.** The birth-commit red run of decision `debt-close-runs-retire` judges a whole test file, not the test the Retire names. A shared file can fail on an old birth commit for reasons unrelated to the debt, so the close passes whatever the named test does. Five debts' Retire lines name `hooks/test_guard.py`.
- **Where.** `lint/check_debt_retire.py`, the birth-commit red run. It has no birth-commit run at this commit.
- **Decision.** `debt-close-runs-retire`, the birth-commit red run it sets. The remedy follows decision `uniform-over-variants`: no second span form.
- **Retire.** Prose, because no test of the birth-commit run exists yet, and a test is code for a builder. The finding closes after two things hold. Each debt that names a shared test file names a test file of its own. A red-then-green test shows the birth-commit run judges only the named file.
