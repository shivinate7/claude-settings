# Drift map, simulator pilot

This is a pilot of the drift audit (owner ask 2026-11-02 13:40 CST). It reads the simulator facts of one parent repo, claude-settings, and compares them with each child repo, in [simulator.md](simulator.md). The pinned shas are: claude-settings `5a5f081eecd931eb4ed72551a18b6154eaaabb60`, q_max `5bbf10e1379ce48058ba68f079e4e3fc4a4e9163`, banchi `46e5c9d9ffc7d226598e39ab13d87c9c44f70b01`, degen `5de5c55d76bdeb9cb8cd8bb3b1ad28bbd9cb89fb`, joyous `53b50465efe23144333df7e2efc23b3ccb706d73`, mailaudit `cd3e12f0a135085f28b63dc04d7f7a1db03839f5`. In a cell, `absent` means the repo was read and does not state the fact. `gap` means the repo or file could not be reached, so it was not read: home `records/duo-simulator.md`, ios-adblock, and mac-memory `degen duo-sim-fold`. `no home` means the parent states no value, so there is no gold value to compare. Gold is the parent value, not proven truth: a child that differs may be right and the parent stale. The result is 21 rows: 14 `same` and 7 `local-nuance`. No row is drifted, the skeptic refuted none, and so there are no lane files.

## Input Needed

None. No row holds a conflict.
