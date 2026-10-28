# c176-home-app-is-home (step c176, home not the retired home-app)

- PR #764 (draft), head a82acedc, up to date with main 599dd58. Batch #763 still open, so no main merge yet; merge main in if it lands first.
- Gates: `bin/verdict ci-job gates --lint --base origin/main` PASS; silent-undo --strict pass (records.md is the generator's output); red recorded on main.
- Review: round 1 (reviewer opus) CHANGES, fixed: the scan now matches the bare name. Round 2 (reviewer sonnet) APPROVE.
- Colour merge: home takes home-app's brand #0a84ff (web/style.css --accent) and leaves rule.drawn; the drawn #8f9e2e is retired.
- Unknown: home paths cited after the rename (web/style.css, ios/HomeApp/Views.swift, SPEC.md) not read in home; the merge may have moved them.
- Notes (not debts): the scan's `/` lookbehind lets a clone path like `~/code/home-app` pass; a bare `home-app.md` mention needs the `records/` prefix; the registry's `about` text is not scanned.
