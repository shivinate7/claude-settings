# sl, chdir and Push-Location are not named leads

- **What.** `sl` and `chdir` are PowerShell aliases of `Set-Location`, and `Push-Location` also changes folder. `harmless_lead` names only `cd` and `Set-Location`, so a chain with these three denies. Safe direction: an over-deny. The owner ruling of 2026-10-15 names only `Set-Location`, so the owner chooses.
- **Where.** `harmless_lead` in `hooks/guard.py`. `_segment_cd_target` in `hooks/guard_core.py` reads none of the three.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** Either the owner names the three as harmless leads, and each gets a row in `hooks/test_guard.py` that asks alone. Or the owner keeps the deny, and the decision says so. The debt then closes with the decision text.
