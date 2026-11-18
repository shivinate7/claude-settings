# Test temp files live in one run folder per test run

## The ruling

Each test run writes temp files only in its own run folder, under one temp root per repo, and removes that folder at teardown.

- One temp root per repo.
- One run folder per test run, named `<pid>-<UUID>`.
- Every helper takes its folder from the run folder. No helper uses the system temp dir directly.
- Teardown removes the run folder.
- The first request of a run sweeps the sibling run folders. It removes a sibling over one day old, whatever its pid. It also removes a sibling over one hour old when its pid is dead. Crashed runs leave these behind. It keeps every other sibling, which parallel runs own. A pid it cannot tell apart from alive counts as alive.
- A test in each repo proves the sweep: an old sibling folder goes, and a new one stays. In this repo, `RunFolderSweepTest` in `lint/test_find_copies.py` also covers a dead pid over an hour old (goes), a dead pid under an hour old (stays) and a live pid over an hour old (stays).
- Rule only. Each repo keeps its own helper (Degen Swift: `TempDirSupport.swift`), and this repo does not check its ages. No code is copied across repos.
- This is a rule for test code, not a guard. No hook enforces it. It binds new temp code and temp code a change touches; older helpers move to it when touched.

Why: on 2026-10-22, test temp folders filled the owner's Mac disk in the Degen Swift repo.

Source: owner, 2026-11-17 13:30 CST, on the own-leftover cleanup goal (`tools-clean-own-leftovers`): each tool clears its own leftovers when it starts.

Risk: incident (2026-10-22).

Kind: process
Home: agents/test-author.md
