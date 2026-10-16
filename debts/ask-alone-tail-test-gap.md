# The harmless-tail rows skip quoted #, /* and a lone apostrophe

- **What.** `hooks/test_guard.py` has ask-alone rows for a quoted `#`, a quoted `/*` and a lone apostrophe. None puts these characters inside a harmless `&& echo` or `; Write-Host` tail. Probes pass today, so a regression in a tail would pass unseen. Rule `building-scanner-respects-strings` asks for these shapes: test every scanner on comment openers and on a lone quote.
- **Where.** `hooks/test_guard.py`, the ask-alone section (j), near the harmless-tail rows.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** Rows put each of a quoted `#`, a quoted `/*` and a lone apostrophe inside an `&& echo` tail and a `; Write-Host` tail. Each row asks alone, and each row goes red on a scanner that treats the character as a comment opener or a quote.
