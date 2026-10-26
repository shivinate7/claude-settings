# c47. One account file for iOS shipping, and no wrapper scripts in the app repos

Written by the advisor, Oct 26. Owner agreed Oct 26. Checked against claude-settings 149f4bc, home-app 0a3419b,
ios-adblock b3d5eb6, degen e2635ca. Two parts, in this order: part 1 in claude-settings, then
part 2 in each app repo after part 1 merges and the Mac has reinstalled.

## Why

`bin/ios-ship` (one shared tool that ships iOS apps) landed Oct 25 (decision
ios-ship-is-one-shared-tool). The build and upload logic now has one home. Two copies remain in
each of the three app repos (home-app, ios-adblock, degen):

1. The account block. `team_id`, `asc_key_id`, `asc_issuer_id`, `asc_key_path` and
   `device_udid` are the same in all three `tools/ios-ship.json` files. A new phone or a key
   rotation means three edits. They cannot move into claude-settings: it is public.
2. The wrappers `tools/testflight` (home-app: `testflight.sh`) and `tools/reinstall-phone-apps`.
   They only find the config and call ios-ship, and they have already drifted: home-app reads
   `APPS=` and `DRY=`; ios-adblock refuses the old `PHONE_APPS_JSON` and has its own test;
   degen passes arguments only. File names differ too.

Rule: one home, then variants (owner, Oct 20): a shared script lives in claude-settings; a repo
keeps only what differs.

## Part 1, claude-settings: ios-ship reads one account file and finds the repo's config

1. Account file. ios-ship reads account values from `~/.config/ios-ship/account.json` (keys as
   today: `team_id`, `device_udid`, `asc_key_path`, `asc_key_id`, `asc_issuer_id`). Order: env,
   then the repo config, then the account file. A repo config may still set a key, as a variant.
   A key unset in all three refuses and names both files and the env var. The file lives only on
   the Mac. No ID goes in this repo: fake IDs in tests only.
2. Default config. `CONFIG` becomes optional. With none given, ios-ship uses
   `<git toplevel of the current folder>/tools/ios-ship.json`. Outside a git repo, or with no such
   file: exit 2 with one line. The usage line and header comment change to match.
3. Old variable. `install` refuses when `PHONE_APPS_JSON` is set (exit 2; message names `--app`
   and `tools/ios-ship.json`), so the ios-adblock wrapper's refusal can go.
4. Rewrite decision ios-ship-is-one-shared-tool in place and README "Shipping iOS apps": where the
   account file lives, what a repo config holds (apps, `repo_url`, overrides), how to call it
   (`ios-ship testflight` from inside the repo).

Proof, test-author first, red on main, in lint/test_ios_ship.sh (the `shell-macos` job):
- account file only: values resolve; repo config key wins over the account file; env wins over both.
- key unset everywhere: refusal names both files.
- no CONFIG inside a repo with tools/ios-ship.json: same calls as passing it; outside a repo: exit 2.
- `PHONE_APPS_JSON` set on install: exit 2, xcodebuild stub never called.

Program logic: a fresh reviewer reads the diff (roles-solo-reviews-logic-diffs-only).

## Part 2, each app repo (home-app, ios-adblock, degen), after part 1 is live on the Mac

1. Once, on the Mac: write `~/.config/ios-ship/account.json` from the values in any one repo
   config (they match). Do not print them.
2. Remove the five account keys from `tools/ios-ship.json`. Keep `apps` and `repo_url`.
3. Delete both wrappers. Point every caller at `ios-ship testflight` / `ios-ship install`:
   degen `Makefile` target `testflight`; home-app `SPEC.md` how-to and its `make testflight`;
   ios-adblock installer docs. ios-adblock: delete tests/test_reinstall_wrapper.sh (it tests the
   wrapper; part 1 moves its case into ios-ship's suite).
4. Proof: `ios-ship install --no-install` from the repo root builds each app (no phone needed),
   and `ios-ship testflight --export-only` archives. Record both verdicts. home-app: its merge grant
   covers this PR; the others need the owner's word to merge.

Not in scope: the vendored design skills (filed under o11, one home for each shared thing).

Report cap: 15 lines per part.
