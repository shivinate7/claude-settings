# One shared tool ships every iOS app, and the API key is documented here

## The ruling

Owner, 2026-10-25: one tool, `bin/ios-ship`, builds and ships the owner's iOS apps from the Mac. Each private app repo calls it with its own config, `tools/ios-ship.json`. This repo documents the App Store Connect API key, so every repo uses the same one (README, "Shipping iOS apps").

- Two jobs share the tool: `testflight` (archive and upload, or export) and `install` (build and install on the phone).
- This repo is public. No team ID, key ID, issuer ID, phone ID or key file goes in it: not in code, tests, docs, commit messages or pull request bodies. Test fixtures use fake IDs.
- The `.p8` key file lives only on the Mac, at `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`, and is never committed. The tool checks that it exists and never reads it.
- The repo root is the git toplevel of the config's folder, never derived from the tool's own path.
- A secret file a build needs (`copy_in`) is copied in for the build only, must be git-ignored at its target, and is removed on every exit path.

Why: a command-line build cannot see the Xcode account ("No Accounts"), so each app repo had its own copy of the key IDs and of a near-identical script. Three copies drifted. One tool gives one place to fix the clean-main check and the cleanup of secret files.

Protected by `lint/test_ios_ship.sh` (the clean-main refusals, the `copy_in` cleanup, the fake-ID fixtures) and the `shell-macos` job in `.github/workflows/gates.yml`.

## Limits

- Unmeasured: a real `xcodebuild`, a real upload, and a real phone. The suite stubs all three. A green run proves the tool's own logic and its calls, not Apple's side.
- The tool is macOS only. `install.ps1` still lands the file on Windows, where nothing runs it.

Kind: process
Home: bin/ios-ship
