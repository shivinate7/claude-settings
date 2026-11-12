# A listed folder's first word is read as the folder

- **What.** `_listed_folder` takes the first non-dash word of a PowerShell listing as the folder. So `gci -Recurse -Filter *.py | % { Set-Content $_.FullName x }` and `ls *.py | % { Set-Content $_.FullName x }` read `*.py` as the folder, and the call allows. A `Where-Object` stage escapes too. This is a common mass-replace idiom, so Claude is likely to write it in normal work.
- **Where.** `hooks/guard_frozen.py`, `_listed_folder`. In the pwsh stack (PRs #2723, #2744, #2753), not yet on main.
- **Decision.** `guard-guards-mistakes-only` (a guard stops Claude's mistakes, not an attacker's forms).
- **Retire.** A test in `hooks/test_guard.py`, red on the current code first, gives the two pipe forms above and a `Where-Object` stage, and expects a refusal for each.
