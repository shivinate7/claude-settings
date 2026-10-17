# The swap1sh install case fails at random on Windows

- **What.** On Windows the copy-mode install case swap1sh failed once with `mv: cannot move guard.py.cs-new` (run 39015490144). The same content passed in run 39014454957.
- **Where.** The install checkout-detection suite, case swap1sh.
- **Decision.** none
- **Retire.** The case passes 20 runs in a row on Windows, or the install retries a replace that Windows refuses.
