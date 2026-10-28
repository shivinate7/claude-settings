# A blind design brief is built from a template

## The ruling

Owner, 2026-10-26 22:58 CDT, on the mailaudit Duo mockups: "not a single one of them tried to break
the mold". Roadmap step c109 (a blind design brief cannot carry today's screen) set the fix.

- Skill `design-explore` builds each blind brief from `skills/design-explore/blind-brief.md`: a
  `Lane kind: blind` line, a `Lane:` line, the free sections Job and Device, and the fixed
  sections House rules and Deliver, word for word. There is no Palette section (below, d4). The Deliver text asks for at least two concepts that
  differ at the root, and one deliberately bold one.
- A free section names none of these: the current product or a view of it, a screenshot or mockup, a
  path or link, the spec or tokens, a keep or match rule. It holds no colour (hex, rgb, hsl), font
  (a font name, family or typeface) or spacing (a px or rem step, a grid) value.
- A blind brief has no Palette section. The blind designer takes colour, type and spacing from the house
  `tokens.md` only, and `agents/designer.md` bars it from `repo-colours.json`, the rest of
  `~/.claude/docs/design/` and the repo's token files. The 4 px step and 8 px radius in `tokens.md` are
  house defaults (`ux-house-rules`), so a blind lane may use them. A repo name in a house file is a
  credit, not a place to look.
- An explore run keeps at least one blind lane. Each informed and directed brief says so in a
  `Blind lanes: <n>` line, or carries `Blind lanes: none, owner: "<the owner's words>"`.
- `hooks/blind_brief.py` holds the check. Skill `design-explore` runs it with `--run` over the folder of
  the run's briefs, with today's view names. As a PreToolUse hook on Agent and Task, it refuses a
  designer spawn whose brief fails, with rule `blind-brief`. A designer brief with no kind line is a
  small change outside the skill, and passes.
- Skill `design-review`, Mockup set check: a design reviewer gives each mockup a structure verdict,
  `same` or `new`. A set that is all `same` is flagged to the owner, with an offer of one more round of
  blind lanes.

Why: the session that drew the Duo mockups ran no blind lane. Its one brief said "Duo layouts must keep
that look", sent the designer to the web app first, and asked for options for each existing view. The
designer kept today's views, so every mockup copied the current app. The prose rule of
`design-agents` could not stop it, because nothing read the brief.

Risk kind: incident, per `building-guard-needs-incident`: 2026-10-26 22:58 CDT, the mailaudit Duo
mockups. Landed 2026-10-27. Second incident, the d4 Banchi phone mockups (the Palette section held a
repo's brand hex), owner gripe 2026-10-28 13:12 CDT: the no-Palette and no-value rules landed in roadmap
step c191. A Device section may name written sizes, so it is exempt from the spacing check.

Limits: the designer's reads are barred by its own instruction, not by a hook: the guard `designer-scope`
limits writes only, and no hook knows the lane kind of a read. A designer that opens a barred file is
caught only by the orchestrator's hex check of the finished mockup. The value patterns catch hex, rgb and
hsl colours, named fonts and font-family words. They also catch a px, rem or dp value anywhere in the Job.
They miss a paraphrase such as "Banchi blue" with no hex, a font that is not on the list and is not named
after the word font, and a short hex such as #fff with no colour word before it. The word lists catch the common forms of a keep rule and of a current-view name, not every
paraphrase. The check refuses a view name only when the orchestrator passes it with `--current`.
The spawn hook does not know view names. The `Blind lanes:` line is the orchestrator's own
count, not a count of spawned lanes.

Cost: one python start per Agent or Task call. It writes no file but the guard.log line of a refusal.

Protected by `hooks/test_blind_brief.py`, with the Duo brief as the red-first fixture.

Kind: process
Home: hooks/blind_brief.py
Home: skills/design-explore/blind-brief.md
