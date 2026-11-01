# Map facts are checked

## The question

How does the plain-English map in `docs/map/` stay true when the code it describes changes?

## The ruling

Owner, 2026-10-30 16:09 CDT. Each pick stands:

- Pilot scope: `mapPaths` in `map.config.json` limits MAP1 (each tracked code file has a map line) to the listed path prefixes. The pilot lists 6 files. The key is one form for every repo.
- Prose shows the same number as its cite. Write "300 s", not "5 minutes".
- Format version 3. A pinned version 2 copy refuses the map. It never passes the map unread.
- A home pointer must resolve: its file is tracked, and the symbol exists in it.
- The term is "fact line", not "claim".

Each number in map prose sits in a fact line. A fact line is an indented list line under a map line. Its prose ends with ` — ` and one backtick cite. The cite is either a value, `[FILE: ]SYMBOL = LITERAL`, or a relation, `uses FILE[:SYMBOL]`.

MAP9, the map check that reads fact lines, lives in `skills/plain-english-map/scripts/map-check.mjs`. It fails when:

- the code and the cite disagree on a value;
- the prose and the cite disagree on a number;
- a symbol, a relation or a home is gone;
- a bare number sits outside backticks in a map line or a trace step, with no cite;
- a reader cannot run. The read is unknown, and it reads FAIL. It never reads PASS.

## Why

Prose that no check reads rots, and it misleads the reader who trusts it.

Banchi, a child repo, was read Oct 30. Its `server concurrency` audit row (banchi's `scripts/docs_audit/code_invariants.py`, function `check_server_concurrency`) proved the backticked `SYMBOL = N` form. A bare 5 there matched inside 15. So MAP9 matches whole numbers only.

## Cost

- Process starts per run: one `node`, the two `git ls-files` reads that exist today, and at most one `python3 -I`. The `python3` start happens only when a fact cites a `.py` file. New: at most one start.
- Files written: none.
- How often: once per CI run of the checks job, and when a session runs the skill's check. Never per commit, tool call or session. No hook and no githook.
- Measured Oct 30 on this branch: 1.2 s wall for MAP1 to MAP9 on the pilot, through `verdict`, with typescript already installed. The CI step runs `npm ci` first, because the map cites `.mjs` files that MAP8 and MAP9 parse.

## Limits

- Other languages (Swift, SQL, shell) use a line regex. It is not a parser.
- MAP2 (each map path is tracked) is not scoped by `mapPaths`. Only MAP1 is.
- Table lines and screen lines are not checked for bare numbers. The plan named them. The code checks map lines and trace steps.
- A second copy inside one repo is a reviewer's call. Copies across repos belong to `lint/find_copies.py`.

Risk kind: likely risk, per `building-guard-needs-incident`. Prose that no check reads rots and misleads. Landed 2026-10-30.
Kind: process
Home: skills/plain-english-map/scripts/map-check.mjs
