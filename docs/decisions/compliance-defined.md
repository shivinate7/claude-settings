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

- It reads the child's tracked `CLAUDE.md` files (in any folder), `AGENTS.md` and `.claude/**/*.md`. It reads Markdown only.
- Live anchors come from `rule_audit.claude_md_anchors(rule_text())` in `lint/rule_audit.py`, never from a copy. A failed read, or zero anchors, gives `unknown` and exit 2.
- A root with the same real path as this repo prints `supersede: n/a - this is claude-settings` and exits 0.
- A line is a departure when it matches one of these wordings, case-insensitive:
  - `never inherited` or `not inherited`
  - `override(s) the global|shared|parent|claude-settings`
  - `instead of the global|shared|parent|claude-settings`
  - `unlike the global|shared|parent|claude-settings`
  - `global|shared|parent|claude-settings rule(s) do(es) not apply`
- A departure line passes when the same line carries `known exemption` and `rule:<id>`, and `<id>` is a live anchor.
- A line that only quotes or agrees with a shared rule has no departure wording, so no flag.
- Each hit is one item line, with the text cut to 160 characters:
  - `departs, no exemption: <file>:<line>: <text>`: departure wording, no valid exemption on the line.
  - `unknown exemption rule:<id>: <file>:<line>: <text>`: `known exemption` with an id that is not a live anchor, or with no id (the id shows as `?`).
  - `redefines rule:<id>: <file>:<line>`: the child holds a rule anchor whose id is a live claude-settings anchor.
  - `known exemption, passes: <file>:<line>: <text>`: a pass line, not a flag.
- Verdicts: `supersede: out - N line(s) to read in M file(s)`, exit 1. `supersede: in shape - M file(s) read`, exit 0.

Risk kind: named incident, per `building-guard-needs-incident`: banchi `CLAUDE.md` line 350 above. Landed 2026-10-31.

Cost: one python start for each run of the skill, on demand. It reads files and writes none. It starts no timer and no long-lived process.

Done check (roadmap step `parent-rules-supersede`): a fixture child repo with a departure line and no exemption is flagged. The same line with the rule named as a known exemption is not. The first case is red on main and green on the fix.

## Not mechanized

No check reads these two. The ruling holds for both.

- A semantic conflict with no override wording: a child line that answers a shared question in other words.
- Hook and code text in the child. Reading it needs a parser, and the check reads Markdown only.

Unmeasured: how many lines the check flags across the owner's child repos.

## Why

A child line that departs from a shared rule, with no exemption named, gives a session two answers to one question. The session can follow the child's line and miss the claude-settings rule.

Fact that would date this record: the wordings above stop matching how child repos write an override.

Kind: build
Plan: docs/decisions/compliance-defined.md#the-ruling (all)
Home: lint/compliance_probes.py
