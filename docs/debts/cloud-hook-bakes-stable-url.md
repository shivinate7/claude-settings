# Cloud refresh hook bakes the stable URL

- **What.** The cloud SessionStart refresh hook is a fixed command that fetches `${RAW}/install.sh`, the URL built when the install ran. If `stable` is later deleted, `curl -f` fails, bash reads no input, and the hook runs nothing and prints nothing. A later `CLAUDE_SETTINGS_REF=main` does not change the hook's URL. The README says the SessionStart hook reads that variable. Only the `install.sh` the hook runs reads it.
- **Where.** `install.sh`: the `HOOK_CMD` line in the cloud block (about line 1046), built from `RAW` (about line 24; `fall_back_to_main` resets it). README, the cloud recovery paragraph (about lines 114-118).
- **Decision.** none
- **Retire.** Close it when a deleted `stable` makes the hook print one WARN line, or when the hook reads `CLAUDE_SETTINGS_REF` at run time. `hooks/test_cloud_setup.sh` must hold a case for the first form, with a deleted `stable`, that passes.
