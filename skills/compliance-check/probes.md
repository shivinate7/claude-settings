# compliance-check probes

Run each from the child's root. `$P` is the parent clone. `$PY` is the Python to use: set it
first with `PY=$(command -v python3 || command -v python)`, since macOS has no `python` and some
hosts have no `python3`. A probe that cannot run is `unknown`. Every probe reads only.

## Parent lints that accept a child path

| Lint | Command | Reads |
| --- | --- | --- |
| `ste_lint.py` | `$PY $P/lint/ste_lint.py --fail-on error --quiet <child *.md>` | STE errors in child prose |
| `check_record_slugs.py` | `$PY $P/lint/compliance_probes.py slugs <child root>` | a record slug over 32 characters that the change adds |
| `check_claude_md_size.py` | `$PY $P/lint/check_claude_md_size.py` | a CLAUDE.md over 200 lines (warns only) |
| `check_agent_models.py` | `$PY $P/lint/check_agent_models.py .claude/agents/*.md` | a Haiku model in agent frontmatter |
| `check_silent_undo.py` | `$PY $P/lint/check_silent_undo.py --repo . --history` | lost lines and reversals on main |

The `slugs` group calls `check_record_slugs.py` on the child's root. It reads the child's own record folders and the files
added against the child's `origin/main`. A long slug already on main is one note line, not a gap. No `origin/main` is `unknown`.

These lints read the parent tree only, and cannot target a child: `rule_audit.py`,
`check_landed_dirs.py`, `check_unknown_reads_contract.py`. `report_guard.py`
is a hook: it already runs in the child's sessions. `ruling_census.py` reads
session transcripts, not a repo.

## Probes per group

| Group | Probe | In shape when |
| --- | --- | --- |
| Outcomes | Read the child `CLAUDE.md` and README first screen. Run `ste_lint` on both | rules name the person served; README passes `fresh-prose` |
| Outcomes | `grep -c "rule:" CLAUDE.md`; look for a check per local rule | each local rule has a hook, test, or CI step |
| Outcomes | `$PY $P/lint/compliance_probes.py supersede .` reads the child's `CLAUDE.md` files, `AGENTS.md` and `.claude/**/*.md` for text that departs from a shared rule (Supersede, below); read each hit in its file | exit 0. A departure passes when its line says "known exemption" and names a live `rule:<id>` |
| Roles | `git log --oneline -40 origin/main` and `git branch -r` | test commits or `tests/*` branches land before product commits |
| Roles | `cat .claude/settings.local.json` | no stale model raise; any raise has `_agentCapUntil` in the future |
| Parallelism | `git worktree list`; `grep -n worktrees .gitignore` | work runs in worktrees; `.claude/worktrees` is ignored |
| Parallelism | `$PY $P/lint/compliance_probes.py lanecap .` reads each brief and plan for a lane cap (rule parallelism-no-guessed-lane-cap); read each hit in its file | exit 0. A cap the owner named passes: the probe passes a line that cites its source, `(owner, ...)` or the owner and a date, and a cap inside a pair of quotes |
| Shared trees | `git stash list` | no output (0 entries) |
| Shared trees | `.claude/launch.json`, dev scripts, `git ls-files '*playwright*.config.*'`, dev server config | each checkout can set its own port and data; each `webServer` has reuse off or absent, or on (any value that can be true, such as `!process.env.CI`) with a wired `globalSetup` that refuses another checkout; port strict (`--strictPort` or `strictPort: true`); no Playwright config: n/a |
| Git | `gh pr list --state merged --limit 20` and `git log --first-parent --no-merges --oneline -20 origin/main` | main moves only by PR |
| Git | `gh api repos/{owner}/{repo}/branches/main/protection`, and `merge.requiredChecks` in `.github/stamp.json` | the answer is known. A 404 is a known answer: no protection. `"protection"` is the right value (decision main-branch-protection, the protection holds the one list): no comparison. When `requiredChecks` is a list, the protection's `required_status_checks.contexts` equal it, else `merge` refuses. No `stamp.json`: no comparison |
| Git | records folders, and `$PY $P/lint/compliance_probes.py slugs <child root>` | one file per record, one folder per kind, no added slug over 32 characters |
| Git | `check_silent_undo.py --history` | no lost lines |
| Verification | `ci-hygiene` skill on `.github/workflows/` | no top finding |
| Verification | `$PY $P/lint/compliance_probes.py playwright .` reads workflows, actions, Makefiles, shell scripts, Dockerfiles, justfiles, Taskfiles, dev container files and package.json scripts | exit 0. No Playwright install runs apt (`--with-deps`, `install-deps`); a repo that does moves to `actions/playwright-setup` (decision one-browser-setup-no-apt, one shared Playwright setup) |
| Verification | list the screens, if any, and the sizes and themes they ship in | a check per screen |
| Verification | `git grep -n sleep`; read each hit in its file and judge it | no waiter loop. A loop that sleeps to wait on a condition is a waiter. A lone delay is not |
| Tokens | none: session practice | `n/a (session)` |
| Building | `git ls-files '*test*'` against product files | each product module has a test |
| Building | designs in `docs/` or `plans/` with no record | each design has a record, or is marked abandoned |
| Speak plainly | `` grep -rnE -e "\bD-?[0-9]+\b" -e "\b[Dd]ecision [a-z0-9]+(-[a-z0-9]+)+" -e "\brecord [a-z0-9]+(-[a-z0-9]+)+" -e "\bD ?\`[a-z0-9]+(-[a-z0-9]+)*\`" --include=*.md . `` finds numbered ids (D12, D-570), keyword cites (Decision draft-until-reviewed) and a D before a backtick slug. `grep -rnwF -f <(basename -s .md decisions/*.md) --include=*.md .` finds bare slugs. `grep -rnE -e "#[0-9]+\b" -e "\b[Ll]ane [0-9]+\b" -e "\b[0-9a-f]{7,40}\b" --include=*.md .` finds PR, issue, lane and commit ids (skip hex words with no digit). Run all from the records parent | each cited id has a short plain name beside it |
| Output | `ste_lint` totals on the child's `*.md` | 0 errors |
| Output | none: known gap. CI's STE step reads Markdown only, so UI copy gets no sentence-length, bloat or double-negative check. The Design probe counts the UI files | report the gap with its count; do not build a UI linter |
| Style | none: `output-styles/shiv-stylisms.md` governs replies, a session act | `n/a (session)` |
| Reports | none: `report_guard.py` covers it | `parent-covered` |

Each probe prints its group line first, then its item lines, the order the scorecard step writes.

## Layout

`$PY $P/lint/compliance_probes.py layout .` reads `lint/layout.json` through
`lint/layout.py`, its one home, plus the child's extras file. Never copy a path from them.

| Line | Means |
| --- | --- |
| `folder <path>/: neither a layout kind nor an extra` | a folder no kind and no extra names. A legacy record folder says where it moves |
| `missing core kind <kind>: <path>` | a core kind of the layout that the child lacks |
| `layout: not rolled out` | the child has no extras file, or its file lacks `"rolled-out": true`. Not a fail. Each line carries `preview`, for the roll-out lane |

Exit 0: in shape or not rolled out. Exit 1: out. Exit 2: unknown. Each top-level dot folder, and
Claude Code's own folders in `.claude/`, count as tool folders, not repo choices, so they pass.
The probe reads tracked files only, so an untracked folder is not there.

## Design

`$PY $P/lint/compliance_probes.py design .` grades each item on its own line, against `docs/design/`
(`checklist.md`, `layout.md`, `tokens.md`). A child with no screen files is `n/a`.

| Item | Pass when |
| --- | --- |
| screens named | `.claude/shoot.json` lists its routes, and `bin/shoot` would accept the file |
| sizes named, themes named | `shoot.json` names them, or takes shoot's default (1440, 820 and 390; light and dark), the house sizes |
| screenshot command | `shoot.json` exists, so the shared `bin/shoot` runs (decision shoot-is-one-shared-command, one shared screenshot command). The repo's own command is `partial` |
| token file | one token source (`tokens.*`, `design-tokens.*`). A test file, and a file that says it is generated, do not count |
| ui copy | never graded: the known STE gap in the Output row |

Then mark `docs/design/checklist.md` for each route in `shoot.json`, at each size and theme.

## iOS

`$PY $P/lint/compliance_probes.py ios .` grades each item on its own line, against the standard in
the `ios-apps` skill. A child with no iOS app (no `project.yml` for iOS, no `.xcodeproj`) is `n/a`.
Comments do not count. Exit 0: in shape or n/a. Exit 1: a gap or a partial.

| Item | Pass when |
| --- | --- |
| make targets | the Makefile has `phone`, `testflight` and `native-check` |
| ship path | `phone` calls `ios-ship install` and `testflight` calls `ios-ship testflight`, with no wrapper script |
| project file | no tracked `.xcodeproj`; XcodeGen writes it from `project.yml`. A tracked one is `partial` |
| kit package | a tracked `Package.swift` holds the app logic. None is `partial` |
| swift 6 | each project file sets `SWIFT_VERSION` 6, no `swift-tools-version` below 6, no language mode 5 |
| ci runner | each macOS image a workflow names, matrix values too, is the pinned image (`IOS_RUNNER`) or a larger runner of it, never `macos-latest` |
| ci checks | a pull-request workflow runs the package tests (when a package exists) and compiles the app. `xcodebuild -showsdks`, `-list`, `-showBuildSettings`, `-help` and `-version` compile nothing |
| slow tests | no workflow runs `make ui-test`, `make native-check`, `sim-test` or an `xcodebuild test` that covers a UI-test bundle (`-only-testing:`, or the scheme's test targets). A run the probe cannot resolve is a gap. UI tests run once per batch on the Mac |
| test diagnostics | each `xcodebuild test` or `test-without-building` run in a workflow, the Makefile or a tracked `*.sh` sets `-collect-test-diagnostics never`, so a failed test starts no `simctl diagnose` of up to 10 minutes. `sim-test` adds it; `build-for-testing` is no run. Named incident, landed 2026-10-29: Restyle and Duo each patched it alone |
| account ids | no `DEVELOPMENT_TEAM` in a project file, Makefile or workflow. An account key of `bin/ios-ship` in `tools/ios-ship.json` is an allowed override: `partial` |

The lowest iOS, the tokens and the test style are read by hand in a repo visit.

## Words

`$PY $P/lint/compliance_probes.py words .` lists each retired word in the child. A retired word is a
"Not" name in a row of `GLOSSARY.md`. The probe reads the child's tracked files only, and never edits
or pushes to the child.

The probe holds no word list. On each run it reads `GLOSSARY.md` and `lint/check_glossary.py` from the
parent clone. It calls the check's own readers: the path read, and the read of identifiers, rule
anchors, record slugs and hook messages. A word the glossary brings back is gone from the next run. A
`word (prose)` name is read in paths, anchors and slugs only, never in a code name. Prose is not read.
A term of the child's own `GLOSSARY.md`, at its root, spans a retired word, as a claude-settings term does.
Terms come only from a four-column `## Terms` table there. Another shape gives no terms.
A child term that repeats a claude-settings term, or is the retired word, does not.

The probe reads every tracked file, so it can take a minute on a large repo. The check reads hook
messages in `hooks/` only. That fits the layout of claude-settings, and a child with another layout has
no message read.

Each hit is one item line, `  <word>: <file>:<line> <detail>`, on one line even when a message holds a
newline. A path hit has `-` for the line. One more line, `glossary read at <sha> of claude-settings`,
names the parent commit whose glossary the run read. It adds `(uncommitted)` when `GLOSSARY.md` differs
from that commit. Name the commit in the report, so a later run on a moved list is read against it.

A tracked file that does not decode as text, such as a binary, is still read by its path. One note line,
`unread: <N> files, <the first three>`, names those files. They do not make the group `unknown`.

| Exit | Group line |
| --- | --- |
| 0 | `words: in shape` |
| 1 | `words: out`, one item line per hit |
| 2 | `words: unknown`: `GLOSSARY.md` cannot be read, it has no rows, a Python file does not parse, no tracked file could be read, or the run passed `WORDS_DEADLINE` (`stopped at <file>, N of M read`) |

A copy of the probe with no `GLOSSARY.md` beside it, such as an installed copy under `~/.claude/lint`,
is `unknown`, never `in shape`.

## Supersede

`$PY $P/lint/compliance_probes.py supersede .` finds child text that departs from a shared rule and names
no known exemption. A claude-settings rule wins over such text. The fix goes in the child: rewrite the
text, or name the exemption.
The probe reads the child's tracked `CLAUDE.md` files (any folder), the root
`AGENTS.md` and `.claude/**/*.md`, a paragraph at a time. Consecutive lines are joined. A fenced code
block is never read. A file reached twice, by a symlink, is read once. It reads Markdown only, and never
edits or pushes to the child.

The probe holds no rule list. On each run it reads the live anchors through `rule_audit.claude_md_anchors`
in the parent clone. A root whose own rule files hold the same anchors is a claude-settings checkout: `n/a`.

Departure wording, in one sentence, in any case:

- a cue (override, overrides, overridden, "instead of", "unlike", "do not apply", "does not apply", and the
  contracted forms) beside a shared rule: global, shared or parent, then a rule noun (rule, ruling, instruction,
  `CLAUDE.md`) within three words; or `claude-settings` alone.
- "never inherited" or "not inherited" beside a rule word: rule, ruling, designation, tier,
  `claude-settings`, `CLAUDE.md`.

Technical prose has none of these: "overrides the parent method", "instead of the global tsc", "Env vars are
not inherited by the worker". A paragraph that only quotes or agrees with a rule is not a hit. A conflict
with no departure wording is read by hand, and so is hook and code text.

| Item line | Means |
| --- | --- |
| `  departs, no exemption: <file>:<line>: <text>` | departure wording, and no valid exemption in the paragraph. `<line>` is the paragraph's first line |
| `  unknown exemption rule:<id>: <file>:<line>: <text>` | the paragraph says "known exemption" or "known exemptions", and the id is no live anchor. With no id (`?`) it counts only beside departure wording: a child's own lint exemption is not ours. A departure paragraph with such an exemption gets this item alone |
| `  redefines rule:<id>: <file>:<line>` | the child holds a `<!-- rule:<id> -->` anchor that is a live claude-settings anchor |
| `  known exemption, passes: <file>:<line>: <text>` | a departure whose paragraph says "known exemption" and names a live `rule:<id>`. Not a hit |

A bare `rule:<id>` with no "known exemption" never passes a departure. Text is cut to 160 characters. N in
`supersede: out - N line(s) to read in M file(s)` counts the flagged items, never the pass lines.

| Exit | Group line |
| --- | --- |
| 0 | `supersede: in shape - M file(s) read`, or `supersede: n/a - this is claude-settings` |
| 1 | `supersede: out - N line(s) to read in M file(s)`, one item line per hit |
| 2 | `supersede: unknown`: the rule text cannot be read, it has no anchor, or a tracked file of the child cannot be read |

## Copies

The copy probe and its verdicts are in `copies.md`, beside this file.
