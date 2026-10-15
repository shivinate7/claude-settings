# The 4 MiB plain-diff output limit is not confirmed in code

- **What.** Output over the host's limit is cut, and the header says "Diff truncated". This repo sets no such limit. It reads the host's `isStdoutTruncated` flag. The 4 MiB figure is not confirmed in code. A diff too large for one `$.process.run` call is an example.
- **Where.** The truncation check in `mods/plain-diff/hooks/register.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** The host limit is confirmed from the host docs or measured, and the decision records the figure.
