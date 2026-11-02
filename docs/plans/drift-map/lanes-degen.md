# Lanes for degen (simulator pilot)

One lane per confirmed drifted row. Gold is the parent value (claude-settings at the pinned sha), not proven truth. Degen's cites are at degen `5de5c55d76bdeb9cb8cd8bb3b1ad28bbd9cb89fb`.

## Lane 1: lock

- Fact key: `lock`. Direction: child-older. Degen text is dated 2026-10-29. The parent text is dated 2026-11-02.
- Edit: `docs/specs/plan.md:2181`.
- Now says: sim-test takes no lock and waits for no CPU load.
- Gold value: sim-test takes one lock per Mac. The lock is the folder `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock`, with the holder's pid in a file named `pid` (`bin/sim-test:7`). One atomic `mkdir` takes it, and it is held for the whole run (`docs/decisions/sim-test-is-the-one-boot-path.md:7`). It is Mac-wide (`README.md:283`).
- Done when: the line states the parent lock, or points at the parent decision, and no longer says "no lock".
- Check first: the same sentence also states the iPhone 18 Pro boot default and the shutdown after the run. Keep those. They are local nuance, not drift.
