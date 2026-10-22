# One layout for every repo (o2): plan

Drafted Oct 22, 2026. Checked at claude-settings 987f682, banchi 6c3a171, q_max b47bd00,
home-app 956e1ab, home 3fbb3d1. The brief for the claude-settings part is
briefs/o2-one-layout.md, and its text sits in o2's ask.

## The test

Can any agent, in any of the five repos, find the right file without being told where it is?
Today it cannot. Three questions decide where a file goes: is it current truth or history? does it
die when the work ships? does every repo have one? (topic t08, folder layout and conventions).

## What the repos look like now (measured)

| Kind | claude-settings | banchi | q_max | home-app | home |
|---|---|---|---|---|---|
| Decisions | `decisions/` (106) | `docs/decisions/` (255, numbered D001-) | `docs/decisions/` (570, incl. `FORMER/`, `RETIRED/`) | none: rulings are CLAUDE.md lines | none |
| Debts | `debts/` (51) | `docs/debts/` (67, numbered 001-) | `docs/debts/` (819), plus `docs/gaps/` (13), `docs/blocked/` (8), `docs/deferred.md` | none | none |
| Plans | `plans/` (1) | inside `docs/specs/` | `specs/` (58), `notes/` (13) | `docs/plan-*.md` (18) and `plans/` (2) | `records/plan.md`, `backlog.md` |
| Specs (how a feature works) | none | `docs/specs/` (55) | mixed into `specs/` | `SPEC.md` | none |
| Design | `ux/` (5, shared ideas) | `docs/DESIGN.md` | `docs/design.md`, `design/` (34), `brand/`, `specs/` design files, `docs/rules/ui-primitives.md` | `docs/design/` (11, mockups and notes) | no UI |
| Tokens | `ux/tokens.md` (ideas) | `app/src/tokens.css` | three layers in `src/` | none | no UI |
| CLAUDE.md lines | 106 | 396 | 182 | 15 | 9 |
| AGENTS.md symlink | n/a | yes | no | no | no |
| `.claude/rules/` | no | no | no | no | no |
| Screenshot command | no | `scripts/screenshot.sh` | no | no | no UI |
| Own extras | `docs/records.md`, `docs/catalog.md` (generated) | `docs/gates/`, `GATES.md`, `TESTS.md`, `agent-traps.md` | `docs/rules/`, `docs/map/` | none | `records/` (ops log, 32) |

Finding: claude-settings's own tools disagree on where records live. `lint/check_record_slugs.py`
(which `hooks/guard.py` reads), `lint/hook_catalog.py` and `lint/check_ruling_kind.py` say the repo
root (`decisions/`); `lint/ste_lint.py` defaults to `docs/decisions`; the stamp action's examples use
both. The path is copied in four places, which the one-constant rule
(building-allow-list-is-the-constant) forbids.

Finding: q_max vendors the map skill at `.claude/skills/plain-english-map` (the drift behind PR 969,
o6) and keeps history folders (`docs/decisions/FORMER`, `RETIRED`) that git already holds.

## The layout

Core, every repo:

- `CLAUDE.md`, 200 lines or fewer (o3); `AGENTS.md` a symlink to it.
- `.claude/rules/` for path-scoped rules (o1).
- `docs/decisions/`: one file per question, current truth. No history folders.
- `docs/debts/` with `README.md` and `notes.md`: known gaps and deferred work, one home.
- `docs/plans/`: work not yet shipped. Deleted when it ships.
- `docs/specs/`: how a shipped feature works now. Outlives the work.
- `docs/records.md`: generated index, as claude-settings has now.

Repos with screens add:

- `docs/design/`: `DESIGN.md`, `mockups/`, `reference/`.
- `tokens/tokens.json` in the W3C format; generated CSS and Swift live where the build reads them,
  marked generated (r2, r3).
- `shots/`, gitignored; the shoot config that d6 (a screenshot command in every repo) names.

A repo's own kinds (home's `records/`, banchi's `docs/gates/`, q_max's `docs/map/`) are allowed when
declared in that repo's layout extras file, so a check can tell an extra from a stray.

One home: the layout lives in one machine-readable file in claude-settings. Every shared tool (the
record-slug check, the records index, the ruling-kind check, STE lint, the guard's record-folder
read, the stamp action, compliance-check's layout group in o4) reads its paths from that file.
A repo adds only its extras.

Why `docs/` and not the repo root: 825 of the 931 decisions in these repos already sit under
`docs/`, so only claude-settings moves its records (157 files), and banchi and q_max move none.
It also clears claude-settings's crowded root.

## Order

1. claude-settings (the brief): the layout file, the tools read it, claude-settings moves its own
   records and `ux/`. Starts after the running cleanup batch lands, since the goal session owns
   claude-settings now and this moves files. c21's repo-wide format and c19's later lanes wait for it.
2. Roll out, one session per repo, smallest risk first:
   - home: add `AGENTS.md`; declare `records/` as an extra. Nothing moves.
   - banchi: `docs/DESIGN.md` to `docs/design/DESIGN.md`; split `docs/specs/` into specs and
     plans (shipped specs stay, unshipped plans move); declare `docs/gates/` as an extra;
     shoot config replaces `scripts/screenshot.sh` (d6). CLAUDE.md shrink is o3.
   - home-app: 20 plan files to `docs/plans/`, deleting shipped ones; `SPEC.md` to
     `docs/specs/`; mockups to `docs/design/mockups/`; add `AGENTS.md`; tokens are r3.
   - q_max: the six design homes to `docs/design/` (r4); `specs/` and `notes/` split into
     specs, plans and debts; `docs/gaps/`, `docs/blocked/` and `docs/deferred.md` fold into debts
     (debts are the one home for deferred work); delete `FORMER/` and `RETIRED/`; the vendored map
     skill is replaced by the pinned shared one (o11); add `AGENTS.md`. Tokens are r2.
3. o4 adds compliance-check's layout group, reading the same file, so a repo that drifts shows red.

Out of scope: record numbering (banchi D001-, q_max D-, claude-settings slugs) stays as each repo
has it, per the decision one-shared-record-stamp ("no existing record is ever renumbered or
renamed"). A move keeps each file name. Volume is out of scope too: folders sort q_max's 1,389
records but do not cull them.

## Open choices

1. Same folders in every repo (pick), or each repo keeps its folders and declares them. Asked on
   Oct 22.
2. `docs/specs/` as its own kind (pick), or specs fold into plans and die on ship. banchi and q_max
   hold about 110 spec files that describe shipped features, so folding them in would lose that
   truth or keep plans that never die.
