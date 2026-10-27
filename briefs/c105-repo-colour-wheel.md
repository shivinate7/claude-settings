# Brief: c105, one shared colour wheel gives every repo its own colour

Repo: shivinate7/claude-settings. One lane, builder then reviewer. Runs beside c100.

## Task
Give every repo one brand colour from one home.
- Registry: `docs/design/repo-colours.json`. It holds the rule and each repo's colour: `{"rule": {...}, "repos": {"<repo>": "#rrggbb"}}`. It is installed with docs/design, so every repo's session reads it.
- One function, `colour_for(repo)`, in one script (for example `lint/repo_colour.py`, CLI `python3 lint/repo_colour.py <repo>` prints the hex). It returns the registry colour when the repo has one. Otherwise it draws one from the name: a hue at least 25 degrees from each state hue (red 5, amber 36, green 145) and at least 30 degrees from every other registered repo's hue. The same name always gives the same hue.
- Fill the registry for the ten repos in scope today: claude-settings, home-app, home, banchi, q_max, degen, ios-adblock, adblock-lists, mailaudit, joyous. Keep a repo's own colour where it has one (banchi's mark palette, mailaudit's parchment, and so on); read it from the repo, never guess.
- The interface for c100: the waiting-page skill passes one hex from `colour_for` to the page. c100 builds the page side. Do not edit `skills/waiting-page/page.html`.

## Rulings
- shiv, Oct 26 20:37 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh28ATeFWrfZMPFYdrqu75pev): the wheel rule above.
- building-one-home-per-capability: one registry and one function; no second copy in the page.

## Failure classes
- A drawn hue that lands within the margins of a state hue or another repo.
- Two runs giving two hues for one name.
- A hue wrap bug at 0 and 360 degrees.

## Check that proves it done
A new test file (stdlib only) goes red on the old tree and green on the new one. It covers the margins, wrap, determinism, a registry hit, and the CLI. Also run lint/rule_audit.py, lint/test_check_landed_dirs.py, lint/hook_catalog.py --check and bin/ste-changed origin/main.

## Report
At most 15 lines: PR, head, red run, green run, review verdict.
