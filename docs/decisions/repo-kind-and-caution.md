# A repo names its app kind and its caution level

## The ruling

Owner, 2026-10-27 00:30 and 00:31 CDT, roadmap step c115: about 1 in 5 home sessions refuse to log in to
the owner's own Home Assistant or KEF speakers. The inconsistency is the pain. Roadmap step c113 asks for
one device list.

- `lint/layout.json` holds the owner's devices, the default device order for each app kind, and three
  caution levels. `ios` is iPhone Duo folded, iPhone Duo unfolded, regular iPhone. `web` is phone width,
  then desktop width.
- A repo names `kind`, `caution` and `visibility` in `.claude/layout-extras.json`, and lists `devices`
  only where it differs. The visibility key is the offline source: no network read decides a level.
- Caution defaults by visibility: `public` for a public repo, `private-solo` for a private one, and
  `unknown` when visibility is missing or unknown. That covers no extras file, no `visibility` key, a
  non-string, `default`, or an unknown value. `unknown` never resolves to `public`.
- `python3 lint/layout.py devices <root>` and `python3 lint/layout.py caution <root>` print the resolved
  values, or `unknown` for a device list when the repo names no kind. An unknown visibility makes
  `caution` print `caution: unknown, the level could not be read`. `lint/layout.py` is the only reader.
- Each level is a set of facts and expected acts. It holds no bypass phrase. `private-solo` says a login to
  the owner's own low-stakes devices works every time, with the credential read by a tool path. Real
  secrets and anything that leaves the machine stay written limits.
- `unknown` carries all the `public` acts, and the fact that visibility is unread. No premise about
  spend or who can read the repo rests on it.
- Agent `designer`, skill `design-explore` and `hooks/blind_brief.py` read the resolved device list. Outside an
  iOS app repo, a mockup draws the first device only. An iOS app repo draws both iPhone Duo poses, the
  folded pose first (skill `ios-apps`). `hooks/session_start.sh` prints the caution level once per
  session, with the `repo ` prefix. An unknown level prints
  `repo caution: unknown, the level could not be read`.
  Skill `compliance-check` lists each repo's own caution rules for the owner to prune.

Why: a session reads a repo's caution from prose it must infer. The same login is refused in one session
and done in the next. A written level removes the guess.

Limits: no device size is written in this repo, so the layout holds none, and no tool draws a size from
it. A size enters only with a written source.

A repo prints its true level only once its extras file names `visibility` or `caution`.
degen, joyous and q_max do not yet.

Risk kind: incident, per `building-guard-needs-incident`. Incidents: the 1 in 5 refused logins above,
2026-10-27; and 2026-11-01 19:30-19:52 CST, when degen, joyous and q_max were private (`gh api` `.private`
true) but had no `visibility` key. Session start printed `repo caution: public`, and a degen lane built a
wrong spend premise on it. Governing rule: `verification-report-unknown-reads` (a read that cannot run is
unknown, never clear or broken). Roadmap step `start-hook-reads-visibility` (session start reads visibility).

Cost: one python start at session start and one at a designer spawn that carries a `cwd`. No network
call. No file is written.

Protected by `lint/test_layout.py` and `hooks/test_session_start.py`.

Kind: process
Home: lint/layout.json
Home: lint/layout.py
