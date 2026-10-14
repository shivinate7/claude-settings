# No test pins the env path or quoted WSLENV forms

- **What.** No test pins the `env:` path form or the quoted-name form of WSLENV.
- **Where.** The WSL guard tests in `hooks/`.
- **Decision.** `wsl-allow-list` (the WSL allow list).
- **Retire.** Add a test for each form. The verdict for each form is recorded in the decision.
