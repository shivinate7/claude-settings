# Test temp files live in one run folder per test run

## The ruling

Each test run writes temp files only in its own run folder, under one temp root per repo, and removes that folder at teardown.

- One temp root per repo.
- One run folder per test run, named `<pid>-<UUID>`.
- Every helper takes its folder from the run folder. No helper uses the system temp dir directly.
- Teardown removes the run folder.
- The first request of a run removes sibling run folders older than one day, which crashed runs leave behind. It keeps newer sibling folders, which parallel runs own.
- A test in each repo proves the sweep: an old sibling folder goes, and a new one stays.
- Rule only. Each repo keeps its own helper (Degen Swift: `TempDirSupport.swift`). No code is copied across repos.
- This is a rule for test code, not a guard. No hook enforces it. It binds new temp code and temp code a change touches; older helpers move to it when touched.

Why: on 2026-10-22, test temp folders filled the owner's Mac disk in the Degen Swift repo.

Risk: incident (2026-10-22).

Kind: process
Home: agents/test-author.md
