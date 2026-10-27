# Outbox: local liaison

- New step (debt, small): `roadmap/build.py` crashes in its upkeep printout on the Mac's system Python 3.9.6. `datetime.fromisoformat` does not take a trailing `Z` before 3.11 (build.py line 123). The page is written first, so only the upkeep and outbox lines are lost. Fix: replace `Z` with `+00:00` before parsing. Measured Oct 27 09:45 CDT.
- Note on the frozen-path override slip (Oct 27): checked main d4e1b86b. The frozen-path refusal already ends with "No override lifts this refusal." (hooks/guard_core.py refuse, override.NO_OVERRIDE, tested in hooks/test_guard.py). No gripe step needed for the message; the slip was the liaison not reading the guard.
