# install.ps1 passes when the only python is the Store alias

- **What.** A machine whose only python is the Store python gets the no-python remedy on every gated call. `install.ps1` still passes, because it counts the alias as python 3.
- **Where.** The python check in `install.ps1`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** Once the Store alias is the only python, `install.ps1` fails, and `install.test.ps1` pins it.
