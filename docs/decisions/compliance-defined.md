# A claude-settings rule wins over a child repo's text

## The ruling

Owner, 2026-10-31 15:04 CDT, waiting-page item 104: a claude-settings rule wins over a child repo's text on the same question, unless that text names the rule as a known exemption.

- Child text is any guard, hook, `CLAUDE.md` line or other text in a child repo.
- Child text that conflicts with how repos inherit from claude-settings, and cites no known exemption, is wrong. It is stale prose for the compliance check to find.
- A known exemption names the claude-settings rule by id, as `rule:<id>`, with the words "known exemption", on the same line.
- A bare mention of `rule:<id>` is no exemption.
- The fix goes in the child repo: rewrite its text, or name the exemption. The claude-settings rule stays as it is.

First case: banchi `CLAUDE.md`, line 350, "The designation is never inherited. A later session re-asks". The roadmap step `parent-rules-supersede` (a claude-settings rule overrides a child repo) names it as a conflict with decision `session-tiers` (the session tiers and how they talk). The line cites no exemption. A banchi lane fixes it.

## The check

Skill `compliance-check` runs probe group `supersede`: `python3 lint/compliance_probes.py supersede <child root>`. `lint/compliance_probes.py` holds the exact patterns.

- It reads the child's tracked `CLAUDE.md` files (in any folder), the root `AGENTS.md` and `.claude/**/*.md`. It reads Markdown only. A tracked file it cannot read gives `unknown`. A file reached twice, by a symlink, is read once.
- The unit is the paragraph: consecutive non-blank lines, joined. A fenced code block (three backticks or three tildes) is never read. An item reports the paragraph's first line.
- Live anchors come from `rule_audit.claude_md_anchors(rule_text())` in `lint/rule_audit.py`, never from a copy. A failed read, or zero anchors, gives `unknown` and exit 2.
- A root whose own rule files hold the same anchors as the live ones is a claude-settings checkout. It prints `supersede: n/a - this is claude-settings` and exits 0.
- Departure wording, case-insensitive, in one sentence. The patterns are narrow, so technical prose ("overrides the parent method", "instead of the global tsc", "Env vars are not inherited by the worker") is no hit:
  - `never inherited` or `not inherited`, when the sentence also holds `rule`, `ruling`, `designation`, `tier`, `claude-settings` or `CLAUDE.md`.
  - a cue (`override(s)`, `overridden`, `instead of`, `unlike`, `do/does not apply`, `don't/doesn't apply`) beside a shared rule. A shared rule is `global`, `shared` or `parent` with a rule noun (`rule(s)`, `ruling(s)`, `CLAUDE.md`, `instruction(s)`) within three words, or `claude-settings` alone.
- A departure paragraph passes when it carries `known exemption` (or `known exemptions`) and `rule:<id>`, and `<id>` is a live anchor.
- A paragraph that only quotes or agrees with a shared rule has no departure wording, so no flag.
- Each hit is one item line, with the text cut to 160 characters:
  - `departs, no exemption: <file>:<line>: <text>`: departure wording, no valid exemption in the paragraph.
  - `unknown exemption rule:<id>: <file>:<line>: <text>`: `known exemption` with an id that is not a live anchor, flagged with or without departure wording. With no id (shown as `?`) it is flagged only beside departure wording, because a child's own lint exemption is not ours. A departure paragraph gets this item alone, not also `departs, no exemption`.
  - `redefines rule:<id>: <file>:<line>`: the child holds a rule anchor whose id is a live claude-settings anchor.
  - `known exemption, passes: <file>:<line>: <text>`: a pass line, not a flag.
- Verdicts: `supersede: out - N line(s) to read in M file(s)`, exit 1. N counts the flagged items only, never the pass lines. M counts every file read. `supersede: in shape - M file(s) read`, exit 0.

Risk kind: named incident, per `building-guard-needs-incident`: banchi `CLAUDE.md` line 350 above. Landed 2026-10-31.

Cost: one python start for each run of the skill, on demand. It reads files and writes none. It starts no timer and no long-lived process.

Done check (roadmap step `parent-rules-supersede`): a fixture child repo with a departure line and no exemption is flagged. The same line with the rule named as a known exemption is not. The first case is red on main and green on the fix.

## Not mechanized

No check reads these three. The ruling holds for all three.

- A semantic conflict with no departure wording: a child line that answers a shared question in other words.
- Hook and code text in the child. Reading it needs a parser, and the check reads Markdown only.
- Which rule an exemption names. The id is not tied to the rule the text departs from, so any live id passes. A negated "no known exemption" reads as a known exemption.

Unmeasured: how many lines the check flags across the owner's child repos.

## Why

A child line that departs from a shared rule, with no exemption named, gives a session two answers to one question. The session can follow the child's line and miss the claude-settings rule.

Fact that would date this record: the wordings above stop matching how child repos depart from a shared rule.

Kind: build
Plan: docs/decisions/compliance-defined.md#the-ruling (all)
Home: lint/compliance_probes.py
