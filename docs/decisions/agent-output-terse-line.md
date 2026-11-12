# Agent output stays short, by one checked line

## Ruling

Plan step R36, "agents write little that no one reads", picks this. Owner, 2026-11-11 12:49 CST, asked how much agents may type. At 12:52 CST the owner left the wording to the session (plan R36). Under that deferral the pick is:

- The one short-output line goes in each agent role file and in the lane start text. Briefs carry none of it.
- The line is the constant `TERSE_LINE` in `lint/check_agent_terse_line.py`. This record does not copy its text.
- A check proves each role file holds the line.
- Reasoning and tool inputs are never cut.

## Mistake

Agents spent output tokens on narration that no reader needed. The plan's read-only audit measured it at 13:06 CST, 2026-11-11. Narration plus the final reply is 19-32% of visible output in standing sessions and 9% in a lane (plan R36).

## Harm it stops

Narration grows each session's context. Cache reads dominate cost. An idle lane re-wrote about 200K tokens of cache for a short answer (plan R36). A role file or the lane text that loses the line, or a new agent file that lands without it, lets that agent narrate again. The check stops that for `agents/*.md` and the lane text. It does not reach a pasted copy.

## What the check reads and refuses

- It reads each file's body text. YAML frontmatter does not count.
- Fenced code (``` or ~~~), HTML comments, inline code spans and 4-space indented code blocks do not count. An indented line that continues a paragraph, or sits in a list item, does count.
- Whitespace collapses, so the line may wrap.
- Exit 0: every file holds the line. It prints nothing.
- Exit 1: a file lacks the line, or a role named in `ROLES` has no file. It names each one. Exit 1 wins over exit 2.
- Exit 2: a file cannot be read, and no file lacks the line. It names each one as unknown.

## Where it lives

- The ten role files: `agents/*.md`, named in `ROLES` in the check. Any other `agents/*.md` file is checked too.
- The lane start text: `skills/project-ops/templates/operating-model.md`.
- A pasted copy in another repo is not read. See the note `terse-line-pasted-copy-unchecked`.

## Cost

- Two `python3` starts per CI run: the check (step "Agent terse line") and its fixture suite (step "Agent terse line fixture suite"). Both are in `.github/workflows/checks.yml`.
- Standard library only. It reads the ten role files and the lane text, 11 files today.
- It writes no file. It keeps no log. It has no hook and no long-lived process.
- Measured 0.0 s wall for the check on this tree, through `verdict`, 2026-11-12 09:38 CST.

## Dated by

The `ROLES` tuple and the `LANE_TEXT` path in the check. If either changes, this record needs a look. The figures in the mistake section come from the 13:06 CST measurement on 2026-11-11.

## Limits

- The check proves the line is present. It does not read the agent's output. The effect on output length is unmeasured.
- Known gaps, each a note: a backslash-escaped backtick reads as a code span (`terse-line-escaped-backtick-false-alarm`). Three indented shapes count as text (`terse-line-bypass-setext-comment-list`). Pasted copies go unread (`terse-line-pasted-copy-unchecked`).

Kind: process
Home: lint/check_agent_terse_line.py
Home: rule:building-guard-needs-incident
