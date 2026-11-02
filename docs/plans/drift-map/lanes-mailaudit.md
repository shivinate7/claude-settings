# Lanes for mailaudit (simulator pilot)

One lane per confirmed drifted row. Gold is the parent value (claude-settings at the pinned sha), not proven truth. Mailaudit's cites are at mailaudit `cd3e12f0a135085f28b63dc04d7f7a1db03839f5`.

## Lane 1: lock

- Fact key: `lock`. Direction: child-older. Mailaudit text is dated 2026-10-30. The parent text is dated 2026-11-02.
- Edit: `docs/decisions/one-simulator-per-mac.md:35`.
- Now says: sim-test takes no lock, waits for no load, and the cap of two booted is not enforced on that path.
- Gold value: sim-test takes one lock per Mac at `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock` (`bin/sim-test:7`). It waits up to 300 seconds for it, then exits 1 (`bin/sim-test:29`).
- Done when: the line states the lock. Check the cap clause against the parent before you change it. The classifier did not judge that clause.

## Lane 2: test-diagnostics-status

- Fact key: `other:test-diagnostics-status`. Direction: child-older. Mailaudit text is dated 2026-10-28. The parent text is dated 2026-11-02.
- Edit: `docs/debts/sim-test-diagnose-and-pin.md:5`.
- Now says: status is open, and sessions add the flag by hand until the sim-test default lands.
- Gold value: sim-test already adds `-collect-test-diagnostics never` unless the caller sets that flag (`bin/sim-test:23`).
- Done when: the debt records the default as landed, and the by-hand step is gone. The debt's own close rule decides whether the file is deleted.
