# Two edge cases pass the mod version gate unbumped

- **What.** A mod folder with a non-ASCII name that the marketplace does not list comes back quoted from git. The gate then misses its base plugin, so an unbumped change passes. When two base folders share one plugin name, the later folder wins. A change to the other folder can then pass unbumped. Found in review round 2 of lane mod-version-gate.
- **Where.** `lint/check_mod_versions.py`, the `ls-tree` read near line 85 and the name map near line 92.
- **Decision.** `ci-unknown-is-red-and-dedup`.
- **Retire.** Read `ls-tree` with `-z`, and fail on a duplicate plugin name. Tests cover both cases.
