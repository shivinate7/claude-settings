# Handoff: lane waiting-data-in-repo (claude-settings)

Wound down by owner instruction, 2026-11-02 12:31 CST, via coordinator session_013NEJL2pASwRjgJDnsvnpNe.

## Goal
Keep a copy of each waiting page's database in the repo, so a page lost to an account or org move can be
rebuilt from files. Incident: 80 items rebuilt from old transcripts. Owner ask 2026-11-02 11:00 CST ("don't take
it verbatim but it is a real gripe of mine"). Scope A+B added 11:49 CST: an artifact registry, a cite check, and an
export of every registered artifact before an account switch.

OWNER HOLD: a draft PR only. It does not merge and joins no batch until the owner says so. Send its head to the
coordinator and to batch runner 7.

## State
- Branch `waiting-data-in-repo`, head b655208f0 before this handoff commit (pushed). No PR is open yet: the next step opens the draft.
- Review: round 1 of 3 FAILED, with 6 must-fixes. Round 2 build (1ab5abea7) fixes all 6. No round-2 review has run yet.
- Suites: the export suite (33 cases) and the layout suite are green after phase 2.
  Compliance suite not re-run by the phase-2 builder.
  Layout.test_this_repo_is_in_shape (lint/test_compliance_probes.py) is red on purpose. It is a true finding
  until the first export lands `waiting/` on origin/roadmap.
- Phase 2 is built (builder, 2026-11-02): layout.artifacts(), lint/check_artifact_cites.py, export_page.py --all,
  two new skill sections, the cite-check suite in checks.yml, the decision record. The Registry, cite-check and All
  suites are green. origin/main is merged in. claude-settings holds no bare artifact link in decisions or debts, so
  nothing moved to `artifact:<id>`. Its roadmap steps hold 14 files with links; `check_artifact_cites.py --steps list`
  lists them for triage.
- No registry entry is written in claude-settings' own extras file yet: the account label is the owner's to name.
- Decision record docs/decisions/waiting-data-in-repo.md (Home: skills/waiting-page/SKILL.md) is on the branch.

## Next steps, in order
1. DONE: phase 2 is built (see State).
2. A test-author records the 11 mutant Red-run trailers: scan, phone, key scan, doc_id scan, number scan, 50-cap,
   900 KB cap, mirror delete, `.complete`, `--allow-empty`, unrolled unread. Mutant reds for phase 2 follow.
3. Review round 2 of 3 (reviewer, Sonnet) of the whole diff. Send it the round-1 findings below.
4. Lane lint: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint`,
   `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`, `~/.claude/bin/merge --lane-lint <pr>`.
5. Open the DRAFT PR, with the "Departs from:" lines below in the body. Send the head to the coordinator and
   batch runner 7.

## Departs from (for the PR body; the coordinator has seen each one)
- Departs from: sketch `records/waiting/` on main. Instead: `waiting/` on the repo's record branch (`roadmap`), because main moves only by PR.
- Departs from: sketch collections items, answers, groups and meta. Adds `asks/` and the page's designData block.
- Departs from: scope A `.claude/artifacts.json`. Instead: an `artifacts` key in `.claude/layout-extras.json`, the one home of the page URL.
- Departs from: scope A "owning account". Instead: a plain label, never an email.
- Departs from: rule-id marker in CLAUDE.md. Instead: no marker; Home is skills/waiting-page/SKILL.md.
- Departs from: "a check refuses bare URLs in roadmap steps". Instead: steps are listed only, because 16 step files hold bare URLs and lanes never write the roadmap. Decisions and debts refuse.
- Coordinator 11:51 CST: briefs and handoffs are working files, outside the cite check.

## Review round 1 must-fixes (all built in 1ab5abea7)
A failed list call could empty the copy. An unknown read on an unrolled repo was shown as clear. Secret shapes were
missed. Phone rule false alarms. The doc_id was not scanned. Two copy paths in SKILL.md.
Verify in round 2: the cost line, and rebuild accepting other folders.

## Open questions
None waits on the owner except the hold itself.

## Not pushed
Nothing. Agent worktrees under .claude/worktrees/agent-* are disposable.

---
## Contract (lane orchestrator spec)
# Lane waiting-data-in-repo: contract

Incident: a waiting page moved to another org; Claude Code lost read access; 80 items were rebuilt
from old transcripts. No repo held a copy of the page database.

## Home of the copy
- The repo's record branch (`lint/layout.py` `record_branch()`, `roadmap` by default; orphan, pushed
  directly, no PR, no CI — skill project-ops). Not main: main moves only by PR (rule git-main-only-by-pr).
- Folder `waiting/` on that branch, a new layout kind `waiting-data` in `lint/layout.json`
  (path `waiting`). Every tool reads the path through `lint/layout.py`; no literal (lint/check_layout.py).
- Layout: `waiting/<collection>/<doc_id>.json`, one file per document (git-record-own-file-per-kind),
  same as `ArtifactData` `out_dir` writes. Collections: `items`, `answers`, `groups`, `asks`, `meta`
  (`meta/page.json`). Plus `waiting/page/designData.json`: the page's designData block
  (mockups live in the page HTML, not the database; read it with `skills/waiting-page/splice.py`).
- JSON written with sorted keys, 2-space indent, trailing newline, so an unchanged doc is byte-identical.

## Script: skills/waiting-page/export_page.py (one home, beside stale_pages.py)
Export mode:
    python3 export_page.py --fetched <dir> --out <waiting dir> [--page <fetched page.html>]
- <dir> holds `<collection>/<doc_id>.json` as `ArtifactData list ... out_dir=<dir>` saves them.
- Each of the five collection folders must exist in <dir> (an empty collection = empty folder).
  A missing folder: verdict `unknown`, exit 2, writes nothing.
- Scan before any write. Parse each file with `json` and scan every string value and every key
  (building-scanner-respects-strings: the parser, not raw text). Finds by shape, not word:
  GitHub token (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_` + body), Anthropic/OpenAI key
  (`sk-` + 20+ key chars), AWS key id (`AKIA` + 16 upper/digits), Slack token (`xox[abprs]-`),
  PEM private key header (`-----BEGIN ... PRIVATE KEY-----`), JWT (three base64url parts, first `eyJ`),
  a cookie or auth header value (`Cookie:`/`Set-Cookie:`/`Authorization: Bearer|Basic` + value),
  `password=`/`passwd=`/`pwd=` + a non-space value, an email address, a phone number
  (10+ digits with optional + ( ) - . spaces, as one run). Words alone ("token budget",
  "password manager", "private key rotation", the owner's first name) never match.
- Any find: verdict `refused`, exit 1, writes nothing. Each find prints one line: file, JSON path,
  kind. Never print the matched value (it would land in logs).
- No find: mirror <dir> into <out>: write changed docs, delete docs no longer fetched, leave
  others untouched. Verdict `changed <n>` (n = files written + deleted) exit 0, or `same` exit 0.
- `--page`: extract the designData block to `page/designData.json`; scanned like the rest.
  A page with no or two designData blocks: `unknown`, exit 2.
- The script never runs git. The session commits (see skill step).
Rebuild mode (the recovery path; must not need the live page — verification-recovery-independent-of-state):
    python3 export_page.py --rebuild <waiting dir> --batches <out dir>
- Writes `<out>/batch-NNN.json`, each a JSON list of at most 50 entries
  `{op: "set", collection, doc_id, data}` covering every doc in <waiting dir> except `page/`.
  Prints `batches <k> docs <n>`. The session sends each file's list as `ArtifactData batch` writes
  to a new page, and splices `page/designData.json` into main's page.html before publishing.
  Missing or empty <waiting dir>: `unknown`, exit 2.

## Layout check
- In lint/layout.py (or the child-repo check it already has): a repo whose extras file has a
  `waiting-page` key and whose record branch has no `waiting/` folder is flagged.
  Read with `git ls-tree` on the local ref then `origin/<branch>`; a ref that is not there
  (shallow CI clone) prints `unknown`, never pass and never fail.

## Skill step (skills/waiting-page/SKILL.md, new section "Keep a copy in the repo")
At each wake and before each republish, the writer: `ArtifactData list` each of the five
collections with `out_dir`, `query.limit` 1000, following `next_cursor` until none; runs export
mode with `--page` on the file "Keep the page on main's code" step 1 already read; on `changed`,
commits `waiting/` on the record branch in its own worktree and pushes. On `refused`: no write,
no commit; the reply names each find, and the item is fixed on the page first. Cost: five list
calls, one python process, one commit when changed. No timer, no watcher.
Recovery: "Rebuild a page from the repo".

## Decision record docs/decisions/waiting-data-in-repo.md
Rule id `waiting-data-in-repo`. Kind, Home, Incidents in the shape of docs/decisions/act-in-place.md.
Number claimed at merge (git-slug-then-claim-number).

## Known limits (state in the record)
- The scan reads shapes. A personal fact in plain words (an employer, a city) passes.
- A truncated fetch (a missed cursor page) deletes docs from the copy; git history keeps them.

## Phase 2 (scope A+B, coordinator 11:49 CST; runs after round-1 fixes)
A. Registry: `artifacts` key in `.claude/layout-extras.json` (lint/layout.py reads it; one home).
   Entry: {id (slug <=32), url, role ("waiting-page" | "queue-page" | other slug), account (plain label, never an email),
   collections (list of collection names to export; waiting-page default = the five), export (path in the record
   branch, default `waiting/` for waiting-page, else `artifacts/<id>/`)}.
   `layout.artifacts(root)` returns the list; `layout.waiting_page(root)` reads the role waiting-page entry first,
   the old `waiting-page` key second. `set_waiting_page` keeps working.
   Cite check: a bare `claude.ai/artifact/` or `claude.ai/code/artifact/` URL in docs/decisions, docs/debts, or a
   roadmap step (record branch roadmap/data/steps/*.json) is refused; cite `artifact:<id>` instead. Unknown id: refused.
   Existing bare URLs in those homes: list them; migrate claude-settings' own in this lane.
B. Export of every registered artifact: export_page.py `--all <repo root> --fetched <dir> --worktree <record worktree>`
   exports each entry's collections into its export path, same scan and mirror rules, one verdict line per artifact.
   Skill step "Before you switch Claude accounts": list each collection with out_dir, touch .complete, run --all, commit, push.
Phase 2 rulings (lane orchestrator, process-only, 12:21 CST):
- P3: missing-name reds stand as the record; named causes come from mutants after build. No stubs.
- --all fetched layout: <fetched>/<artifact id>/<collection>/ (+ .complete). A waiting-page entry with <fetched>/<id>/page.html exports its designData as in single mode.
- Cite check: decisions and debts refuse; roadmap steps (all string fields, note and ask included) are listed only, exit 0, for triage to migrate. Migrate claude-settings' own decisions/debts bare URLs in this lane, registering each URL.
- set_waiting_page with a role entry present: updates that entry's url.
- Registry problems (email account, duplicate id, id > 32 chars) raise LayoutError from artifacts().
- Add the new suite to checks.yml.

## Round 2 brief
# Round 2 fixes (lane orchestrator rulings, process-only, 11:45 CST)
Branch waiting-data-in-repo at 87e355942 carries red tests for each item below.
1. `.complete` marker per collection; missing -> unknown exit 2; emptying a collection that has copy docs -> unknown unless `--allow-empty <collection>`.
2. lint/compliance_probes.py probe_layout: an unread copy on a not-rolled-out repo reports unknown (append `unread` before the `if not rolled:` return).
3. New scan shapes: URL query secrets (access_token, key, sig, token), `*_PASSWORD=` / `password:` / `pwd =` forms, Google `AIzaSy`, Stripe `sk_live_`/`rk_live_`, GitLab `glpat-`, AWS `ASIA`, `connect.sid=`. Scan doc_ids (file names) and JSON numbers: a 10-11 digit integer is a phone; 13-14 digits is not (epoch ms).
4. Phone in strings narrowed: `+<cc>` with separated groups, `(xxx) xxx-xxxx`, or 3-3-4 digits joined by `-` `.` or space. No bare digit runs. `btn-sk-...` must not match the api-key shape.
5. Rebuild: each batch also under 900,000 bytes; one doc over that -> unknown. Only the five collections and `page/` are accepted.
6. Any crash: exit 3, one `unknown` line.
7. SKILL.md: a list call that errors, or ends with a cursor still pending, stops the run (no `.complete`, no export). One copy path only: the record worktree (SKILL.md:114 vs :119 disagree). Put the copy step before the republish step. The cost line says "one list call per page of each collection".
Known open: `Layout.test_this_repo_is_in_shape` is a true finding until the first export lands on the roadmap branch; leave it red if so and say so.

Round-1 builder report (prior agent, for context): export_page.py built with its own scanner (none existed in hooks/ or lint/); layout check lives in lint/compliance_probes.py `waiting_copy()`/`git_ok()`; kind `waiting-data` set `waiting`; checks.yml step after the splice suite; docs/map needs no entry.
