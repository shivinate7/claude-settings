# The schtasks install test is not in any CI job

- **What.** `janitor/test_install_schtasks.py` was not wired into any CI job. Its skip has never run on Windows CI. It is proven only on this machine, by hand.
- **Where.** `janitor/test_install_schtasks.py` and the CI workflow files.
- **Decision.** `list-form-subprocess-ignores-a-path-shim-on-windows` (a list-form subprocess call ignores a PATH shim on Windows).
- **Retire.** A Windows CI job runs `janitor/test_install_schtasks.py`, and it goes green.
