# One shared tool ships every iOS app, and the API key is documented here

## The ruling

Owner, 2026-10-25: one tool, `bin/ios-ship`, builds and ships the owner's iOS apps from the Mac. The account values (team, phone and API key IDs, and the key path) live once, in `~/.config/ios-ship/account.json` on the Mac. Each private app repo keeps only what differs, in `tools/ios-ship.json`: its apps, `repo_url`, and any account key it overrides. The app repos run `ios-ship testflight`, `ios-ship install` or `ios-ship profile` from inside the repo, with no wrapper script. This repo documents the App Store Connect API key, so every repo uses the same one (README, "Shipping iOS apps").

- Three jobs share the tool: `testflight` (archive and upload, or export), `install` (build and install on the phone) and `profile` (record one app with Instruments on the phone).
- `profile` records by the phone's UDID, never by name. When `xctrace` fails with "Waiting for device to boot", it retries once after a fixed wait (60 s by default). Owner, 2026-10-26: retry once, with no wait on a device state. The phone showed `available (paired)` before and after a failed recording, so no state predicts the failure. Any other failure is not retried.
- This repo is public. No team ID, key ID, issuer ID, phone ID or key file goes in it: not in code, tests, docs, commit messages or pull request bodies. Test fixtures use fake IDs.
- The `.p8` key file lives only on the Mac, at `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`, and is never committed. The tool checks that it exists and never reads it.
- An account value comes from the environment, then the repo config, then the account file. A value unset in all three is refused, and the refusal names both files.
- With no config path given, the config is `tools/ios-ship.json` at the git toplevel of the current folder. The repo root is the git toplevel of the config's folder, never derived from the tool's own path.
- `install` refuses the old `PHONE_APPS_JSON` variable, so no app repo needs its own refusal.
- A secret file a build needs (`copy_in`) is copied in for the build only, must be git-ignored at its target, and is removed on every exit path.

Why: a command-line build cannot see the Xcode account ("No Accounts"), so each app repo had its own copy of the key IDs and of a near-identical script. Three copies drifted. One tool gives one place to fix the clean-main check and the cleanup of secret files. One account file means that a new phone or a key rotation is one edit, not three. It cannot live in this repo, which is public.

Protected by `lint/test_ios_ship.sh` (the clean-main refusals, the `copy_in` cleanup, the account-file order, the default config, the profile retry, the fake-ID fixtures) and the `shell-macos` job in `.github/workflows/checks.yml`.

## Limits

- Unmeasured: a real `xcodebuild`, a real upload, a real phone, and whether one retry clears the boot wait (the live check on the Mac, roadmap step c48, "ios-ship gets a profile job"). The suite stubs all three. A green run proves the tool's own logic and its calls, not Apple's side.
- The tool is macOS only. `install.ps1` still lands the file on Windows, where nothing runs it.

Kind: process
Home: bin/ios-ship
