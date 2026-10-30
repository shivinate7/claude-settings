# CI pins of claude-settings actions follow the session's tools

## The ruling

Owner, 2026-10-26 (gripe on the degen Duo batch): "doesn't this just mean CI is old? why would we conform". A child repo's CI and a local session run the same claude-settings tools. When they differ, the pin moves; the prose does not conform to the old pin.

Outcome protected: a lane never loses a CI run, or its place in the batch, to a lint that claude-settings main already replaced.

## The design

- Rule `git-integration-branch-merge`: a CI lint red that `bin/ste-changed` passes, while it blames an old ste-lint pin, is not a strike. The session moves that pin to claude-settings main in a lane of its own, with no question. Its reviewer checks only that the lane changes pin lines alone, to a main commit that descends from the old pin. claude-settings main already reviewed the lint change. Other action pins keep the normal rule, because they are checks with no local twin.
- A commented-out pin is not a pin.
- `bin/ste-changed` lints and reads pins from one checkout: the one beside its real path when that holds `actions/ste-lint`, else the one the global CLAUDE.md points at (hooks/guard_pointer.py `pointer_checkout`). A copy install has no `actions/` and is no git repo.
- `bin/ste-changed` reads each `claude-settings/actions/ste-lint@<sha>` pin in the linted repo's `.github/workflows`. It compares the files the step runs (`LINT_FILES`) at the pin with this copy's. On a difference it prints the pin, its date, its line and the remedy, and exits 3 even when the lint passed. An equal pin prints one line and changes nothing. A pin this clone does not hold is unknown and changes no exit code.
- Pins stay current on demand: the session that runs the tool sees the drift and moves the pin. No bot and no schedule. Rule `outcomes-mechanize-rules` allows on-demand reads, never a timer.

## Why not a bot

- Dependabot: it does not bump these pins. Read from dependabot-core's source at f0feb6f (2026-10-26), not run live: `UpdateChecker#latest_commit_sha` in `github_actions/lib/dependabot/github_actions/update_checker.rb` returns nothing when the action's repo has no version tag. claude-settings has no tags (`git ls-remote --tags`, 2026-10-26).
- A scheduled bump PR, like ios-adblock's `pin-bump.yml`: it opens a PR in each child repo on a timer, whether or not a session works there. Each bump moves a check's verdict with nobody reading it.
- Renovate's `git-refs` manager, as `renovate.json` uses for one pin here, could track main. It needs the Renovate app in each child repo, which is unknown. Revisit it if drift still costs CI runs after this lands.

## Safety holes, named

- (a) Only `ste-lint` is checked. `stamp`, `readme-links`, `all-jobs-passed`, `ci-alarm` and `ruling-kind` pins can drift unseen. `ste-lint` is the one with a local twin that a session runs.
- (b) A session that never runs `bin/ste-changed` before a push still meets the old pin in CI. The rule covers that red.
- (c) Moving each child repo's pins waits for the owner's plan for each repo (step c76, child-repo part).
- (d) Any byte change in `LINT_FILES` is drift, a comment edit too. The line says a line can pass here and fail CI, not that one will.
- (e) The check reads the commit at the clone's HEAD. It misses lint edits that are not yet committed.

Kind: process
Home: bin/ste-changed
