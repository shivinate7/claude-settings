# Hook, judge, mod and skill catalog

This page says what each hook, judge, mod and skill in this repo does. A script writes it. Do not edit it by hand.

Run `python3 lint/hook_catalog.py` to write the page again. CI runs `python3 lint/hook_catalog.py --check`. The check fails when the page is stale or a source text is empty.

Where each text comes from:

- A hook runs a script. Its text is the first paragraph of the script docstring, or the leading comment block of a shell script. A hook whose command is inline shell has no script, so its text is one line in `lint/hook_catalog_inline.json`, under its event and matcher.
- A judge is a prompt hook that a model answers. Its key is the first sentence of the prompt. Its text is the rest of the prompt, up to the standard clause that blocks only on a clear breach.
- A mod is an enabled mod from this repo. Its text is the intro of its `README.md`. A mod with no README takes the `description` in its `plugin.json`, then the text of its `SOURCE.md`.
- A skill is a folder under `skills/`. Its text is the `description` in its `SKILL.md` frontmatter.

Model and effort come from the model table (decision `subagent-model-cap`, the model per role). A hook with no row in that table calls no model, so its row says "no model". A judge takes the `model` field of its prompt hook, and a prompt hook has no effort field. A skill has no model pin, so its row says "no model" and effort "none". The model table has no row for a mod, so a mod row says "not listed". A mod may still call a model.

## Hooks and judges

| Key | Kind | Event | Matcher | If | Model | Effort | What it does |
|---|---|---|---|---|---|---|---|
| `hooks/decision_watch.py` | hook | Stop | - | - | haiku | xhigh | Claude Code hook: decision/gate/settings watch (Stop). Replaces the `type: agent` guardrail. |
| `hooks/stall_watch.py` | hook | Stop | - | - | no model | n/a | Stall watch for background Bash commands. Standard library only. |
| `lint/report_gate.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: report-shape gate. |
| `lint/md_sweep.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: markdown sweep (Stop). |
| `hooks/config_watch.py` | hook | Stop | - | - | no model | n/a | The PostToolUse and Stop watch on the subagent model cap. |
| `hooks/ruling_home.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: ruling-home check (Stop). |
| `hooks/precompact_handoff.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: get the session's handoff ready before compaction. |
| `hooks/reply_judge.py` | hook | Stop | - | - | haiku | xhigh | Claude Code hook: reply judge (Stop). Judges the final reply against three style rules. |
| `hooks/feedback_gate.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: feedback inbox gate (Stop). Decision owner-feedback-inbox. |
| `hooks/reread_check.py` | hook | Stop | - | - | no model | n/a | Claude Code hook: after compaction, check the session re-read its handoff. |
| `hooks/precompact_handoff.py` | hook | PreCompact | - | - | no model | n/a | Claude Code hook: get the session's handoff ready before compaction. |
| `hooks/precompact_handoff.py` | hook | SessionStart | compact | - | no model | n/a | Claude Code hook: get the session's handoff ready before compaction. |
| `hooks/precompact_handoff.py` | hook | SessionStart | clear\|fork | - | no model | n/a | Claude Code hook: get the session's handoff ready before compaction. |
| `inline: SessionStart matcher=startup\|resume` | hook | SessionStart | startup\|resume | - | no model | n/a | Pulls the claude-settings clone with a fast-forward pull, then runs its install.sh. Does nothing in cloud sessions. A failed pull or install falls through, and the command always exits 0. |
| `hooks/session_start.sh` | hook | SessionStart | startup\|resume | - | no model | n/a | Prints "checkout `<toplevel>` on `<branch>`, `<n>` dirty files" at session start and resume. Also warns when the global rules differ from this checkout, the claude-settings clone is off main or behind origin/main, this repo's default branch is behind origin, a freshness check could not run, or the SessionEnd sweep is disarmed or unknown. Silent outside a git tree or when git is missing. Always exits 0, nothing on stderr. |
| `janitor/session_end_sweep.py` | hook | SessionEnd | - | - | no model | n/a | Claude Code hook: SessionEnd trigger for janitor/sweep.py. |
| `hooks/precompact_handoff.py` | hook | SessionEnd | clear | - | no model | n/a | Claude Code hook: get the session's handoff ready before compaction. |
| `janitor/agent_end_reap.py` | hook | SubagentStop | - | - | no model | n/a | Claude Code hook: stop the processes a finished subagent left in its own worktree. |
| `hooks/guard.py` | hook | SubagentStop | - | - | no model | n/a | The global PreToolUse guard. |
| `hooks/guard.py` | hook | PreToolUse | Bash\|PowerShell\|Edit\|Write\|MultiEdit\|NotebookEdit\|Agent\|Task\|Workflow\|Skill\|mcp__ccd_session__start_session\|mcp__Claude_Code_iOS_Simulator__control | - | no model | n/a | The global PreToolUse guard. |
| `hooks/stall_watch.py` | hook | PreToolUse | Bash | - | no model | n/a | Stall watch for background Bash commands. Standard library only. |
| `lint/ste_gate.py` | hook | PreToolUse | Write\|Edit\|MultiEdit | - | no model | n/a | Claude Code hook: Simplified Technical English gate. |
| `Judge this AskUserQuestion call: $ARGUMENTS` | judge | PreToolUse | AskUserQuestion | - | claude-sonnet-5-5 | n/a | Answer {"ok": true} at once for a clarifying question. Judge only a choice between real alternatives that have consequences. Rules: style-option-says-effect (each option says what the user gains and loses), style-question-states-problem (the question states the problem and why it needs the user's word), output-bring-decisions-as-question (a decision is a question with options and a recommendation). |
| `hooks/question_outcome.py` | hook | PreToolUse | AskUserQuestion | - | haiku | xhigh | PreToolUse hook for AskUserQuestion: each question passes an outcome check first. |
| `Judge this subagent spawn: $ARGUMENTS` | judge | PreToolUse | Agent | - | claude-sonnet-5-5 | n/a | Answer {"ok": true} at once when subagent_type is claude-code-guide, when the call resumes an existing agent, or when a non-Explore brief is under 60 words. For an Explore spawn, block only when the brief asks it to audit, review, judge, rate or compare meaning (not only to find files, names or text) and the call does not set model sonnet; the fix is model sonnet with effort high (subagent-model-cap, audit Explore row). Otherwise answer {"ok": true} for Explore. Only for builder, reviewer, and test-author briefs, apply roles-brief-contents (the brief carries the task, the files, governing rulings, and the check that proves done) and tokens-point-brief-at-files (the brief names files and never pastes their contents). |
| `Judge this edit to a file: $ARGUMENTS` | judge | PreToolUse | Edit | Edit(**/decisions/**) | claude-sonnet-5-5 | n/a | Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, and no superseded ruling kept beside the new one). A record may state a current fact with its history in one clause; that is not a breach. Rule: rulings-declare-kind (refuse only an edit whose new text deletes a `Kind:`, `Plan:` or `Home:` line, or adds a ruling section with no `Kind:` line in the same text; you see only the changed text, so never refuse for a Kind line you cannot see). |
| `Judge this edit to a file: $ARGUMENTS` | judge | PreToolUse | Write | Write(**/decisions/**) | claude-sonnet-5-5 | n/a | Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, and no superseded ruling kept beside the new one). A record may state a current fact with its history in one clause; that is not a breach. Rule: rulings-declare-kind (refuse a decision record that has no `Kind: build` with `Plan: <path>#<slug> (<platform>)` lines, or `Kind: process` with a `Home:` line). |
| `Judge this SendMessage call: $ARGUMENTS` | judge | PreToolUse | SendMessage | - | claude-sonnet-5-5 | n/a | Answer {"ok": true} at once for a resume, a status message, or an orchestrator instruction. Rule: parallelism-no-mid-task-talk (a lane messages a peer only when the branch must hear something that changes its work). You cannot see the receiver's task, so judge by wording only. |
| `hooks/sim_boot_record.py` | hook | PreToolUse | Bash\|mcp__Claude_Code_iOS_Simulator__control | - | no model | n/a | Record each simulator a session call booted (decisions/sweep-shuts-down-idle-simulators.md, ruling 1). |
| `hooks/reread_check.py` | hook | PreToolUse | Read | - | no model | n/a | Claude Code hook: after compaction, check the session re-read its handoff. |
| `hooks/rm_prompt_answer.py` | hook | PermissionRequest | Bash | - | no model | n/a | PermissionRequest hook on Bash: answer allow for a guarded delete of a bound, safe path. |
| `hooks/agent_brief.py` | hook | SubagentStart | - | - | no model | n/a | SubagentStart hook: give every spawned agent the standing rules, so briefs stop retyping them. |
| `hooks/local_time.py` | hook | SubagentStart | - | - | no model | n/a | UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also captures owner feedback: a prompt that opens with `fb` is saved to the session's inbox file until a prompt of `fb done`. |
| `hooks/local_time.py` | hook | UserPromptSubmit | - | - | no model | n/a | UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also captures owner feedback: a prompt that opens with `fb` is saved to the session's inbox file until a prompt of `fb done`. |
| `hooks/config_watch.py` | hook | PostToolUse | Bash\|PowerShell\|Write\|Edit\|MultiEdit\|NotebookEdit | - | no model | n/a | The PostToolUse and Stop watch on the subagent model cap. |
| `hooks/ci_wake.py` | hook | PostToolUse | Bash\|PowerShell | - | no model | n/a | CI wake-up hook. Standard library only. See decisions/handoff-hooks-wave-2.md, part 3. |
| `hooks/sim_boot_record.py` | hook | PostToolUse | Bash\|mcp__Claude_Code_iOS_Simulator__control | - | no model | n/a | Record each simulator a session call booted (decisions/sweep-shuts-down-idle-simulators.md, ruling 1). |
| `hooks/reread_check.py` | hook | PostCompact | - | - | no model | n/a | Claude Code hook: after compaction, check the session re-read its handoff. |

## Mods

| Key | Kind | Event | Matcher | If | Model | Effort | What it does |
|---|---|---|---|---|---|---|---|
| `mods/token-weather` | mod | - | - | - | not listed | not listed | A live forecast of the context window, drawn above the prompt: a weather icon, the fill percentage, and a chart of the last turns. Source: Repo: https://github.com/anthropics/claude-code-playground Path: claude-code/mods/token-weather Commit: 569c5283d9a0a7ee7938df85bb32e4f48cbb8c86 Licence: Apache-2.0 (LICENSE is the repo-root file) Vendored on 2026-10-12. Copied unmodified; markdown docs and unused screenshots omitted. |
| `mods/desktop-statusline` | mod | - | - | - | not listed | not listed | Status band above the prompt in the Claude Desktop app's Code tab: folder, git branch and state, session age, prompt count and cost, a context meter, 5-hour and weekly plan usage limit meters with reset countdowns, last-turn model, duration and cache hit rate, idle time against the prompt-cache TTL, compactions, and running agents. Toasts at 80% and 95% of a usage limit. Draws only on the desktop surface, so a CLI statusLine is left alone. Source: Repo: https://github.com/centminmod/claude-plugins Path: plugins/desktop-statusline Commit: 5239dd5c241ca5537f4737c25321399734d0c0bc Licence: MIT (LICENSE is the plugin-folder file) Vendored on 2026-10-12. Copied unmodified; markdown docs and unused screenshots omitted. |
| `mods/plain-diff` | mod | - | - | - | not listed | not listed | A mod. It adds one command, `/plain-diff`. It draws nothing else. The command opens a pane. The pane lists each changed file. Each file has a short note in plain English above its diff. The note says what changed and why it matters. |
| `mods/session-board` | mod | - | - | - | not listed | not listed | A mod. It adds two commands, `/board` and `/safe-stop`. It draws nothing else. It calls no model. |

## Skills

| Key | Kind | Event | Matcher | If | Model | Effort | What it does |
|---|---|---|---|---|---|---|---|
| `skills/ci-hygiene` | skill | - | - | - | no model | none | Use when a session creates or edits CI config (GitHub Actions, workflow files, .github/workflows, other CI files), or when the user says CI is slow, queued, or flaky, or says "ci-hygiene". Not for ordinary code edits. Keeps CI fast, cheap, and trusted. |
| `skills/compliance-check` | skill | - | - | - | no model | none | Use when the user asks how well a repo follows the global rules, or says "compliance check", "audit this repo against CLAUDE.md", or "bring this repo into shape". Not for ordinary code edits. Reads the repo, scores it per rule group, and gives a ranked plan of lanes. |
| `skills/design-review` | skill | - | - | - | no model | none | Use after a change to a screen in a repo that has screens. Runs two blind design reviews of the changed pages, then compares them with the repo's design records. Not for a change that has no screen. |
| `skills/fresh-prose` | skill | - | - | - | no model | none | Use when a session writes or updates a README, docs, CLAUDE.md, agent files, or decision records, or when the user says "stale docs" or "fresh-prose". Makes prose hard to go stale, by binding each claim to a check. |
| `skills/impeccable` | skill | - | - | - | no model | none | Use when the user wants to design, redesign, shape, critique, audit, polish, clarify, distill, harden, optimize, adapt, animate, colorize, extract, or otherwise improve a frontend interface. Covers websites, landing pages, dashboards, product UI, app shells, components, forms, settings, onboarding, and empty states. Handles UX review, visual hierarchy, information architecture, cognitive load, accessibility, performance, responsive behavior, theming, anti-patterns, typography, fonts, spacing, layout, alignment, color, motion, micro-interactions, UX copy, error states, edge cases, i18n, and reusable design systems or tokens. Also use for bland designs that need to become bolder or more delightful, loud designs that should become quieter, live browser iteration on UI elements, or ambitious visual effects that should feel technically extraordinary. Not for backend-only or non-UI tasks. |

## External plugins

These plugins are enabled in `settings.json`. They are not in this repo, so this page gives no description.

- ponytail: not in this repo
- frontend-design: not in this repo
