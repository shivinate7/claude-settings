# The PowerShell here-string scan is slow on many unclosed openers

- **What.** The guard finds PowerShell here-strings with a lazy match. An unclosed opener makes the match read on to the end of the command. So the time grows with the square of the number of openers. Measured in review: 5000 openers (15 KB) take 0.54 s, and 20000 openers (60 KB) take 9 s. Real scripts do not hold so many unclosed openers. A slow guard fails open (debt guard-timeout-fails-open).
- **Where.** `_HERE_STRING` in `hooks/guard.py`, used for the PowerShell tool only.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill).
- **Retire.** Find here-strings with one linear pass, or cap the text length that the scan reads. A command with 20000 unclosed openers then takes under 0.05 s.
