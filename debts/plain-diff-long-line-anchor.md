# The end-of-line anchor can match at a chunk end

- **What.** On a line over 3000 characters, the end-of-line anchor can match at a chunk end. This adds a false positive only. A minified line over 3000 characters with `token` near a chunk end is an example.
- **Where.** The chunk split in the content test of `mods/plain-diff/hooks/lib.mjs` (`looksSecret`).
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** A case with `token` near a chunk end passes, and the anchor does not match at the chunk end.
