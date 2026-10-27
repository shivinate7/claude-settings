# A repo names its app kind and its caution level

## The ruling

Owner, 2026-10-27 00:30 and 00:31 CDT, roadmap step c115: about 1 in 5 home sessions refuse to log in to
the owner's own Home Assistant or KEF speakers. The inconsistency is the pain. Roadmap step c113 asks for
one device list.

- `lint/layout.json` holds the owner's devices, the default device order for each app kind, and two
  caution levels. `ios` is iPhone Duo folded, iPhone Duo unfolded, regular iPhone. `web` is phone width,
  then desktop width.
- A repo names `kind`, `caution` and `visibility` in `.claude/layout-extras.json`, and lists `devices`
  only where it differs. The visibility key is the offline source: no network read decides a level.
- Caution defaults by visibility: `public` for a public repo, `private-solo` for a private one, and
  `public` when visibility is unknown or the extras file is missing.
- `python3 lint/layout.py devices <root>` and `python3 lint/layout.py caution <root>` print the resolved
  values, or `unknown` for a device list when the repo names no kind. `lint/layout.py` is the only reader.
- Each level is a set of facts and expected acts. It holds no bypass phrase. `private-solo` says a login to
  the owner's own low-stakes devices works every time, with the credential read by a tool path. Real
  secrets and anything that leaves the machine stay written limits.
- Agent `designer`, skill `design-explore` and `hooks/blind_brief.py` read the resolved device list. A
  mockup draws the first device only. `hooks/session_start.sh` prints the caution level once per session.
  Skill `compliance-check` lists each repo's own caution rules for the owner to prune.

Why: a session reads a repo's caution from prose it must infer. The same login is refused in one session
and done in the next. A written level removes the guess.

Limits: no device size is written in this repo, so the layout holds none, and no tool draws a size from
it. A size enters only with a written source.

Risk kind: incident, per `building-guard-needs-incident`: the 1 in 5 refused logins above, 2026-10-27.

Cost: one python start at session start and one at a designer spawn that carries a `cwd`. No file is written.

Protected by `lint/test_layout.py` and `hooks/test_blind_brief.py`.

Kind: process
Home: lint/layout.json
Home: lint/layout.py
