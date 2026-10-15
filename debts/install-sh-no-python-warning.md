# install.sh gives no warning when python3 is missing

- **What.** A Mac without `python3` gets no warning from `install.sh`. Every gated call is then refused with the no-python remedy.
- **Where.** `install.sh` (the python check).
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** Once python3 is missing, `install.sh` warns, and a test pins the warning.
