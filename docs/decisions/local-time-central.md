# Sessions speak times in US Central

## The ruling

Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. It says "21:40 CDT", never a
UTC time and never a 12-hour time.
Every clock time the session gives the owner names its zone, each time, not once per message (owner, 2026-11-02 13:10 CST).

`hooks/local_time.py` gives each session the current Central time as one line, for example `Local time: 2026-10-13 21:40 CDT (UTC-05:00)`.
In winter the line reads CST and UTC-06:00.

- `UserPromptSubmit` runs it on every prompt. `SubagentStart` runs it with `--agent`, which prints `hookSpecificOutput.additionalContext`
  JSON and never reads stdin.
- The hook codes the US rule: DST runs from the second Sunday of March to the first Sunday of November, at 02:00 local. It reads neither
  zoneinfo (Python on Windows often has no tz database) nor the machine zone.
- The hook is advisory. On an internal error it prints nothing to stdout, writes one `local_time:` line to stderr, and exits 0. It prints
  the time line before it reads stdin to save the owner's message (`owner-feedback-inbox`).

Reason: sessions saw only UTC and answered in UTC, which shows the wrong date for the owner every evening.

Kind: process
Home: hooks/local_time.py

## A message's own time matches the clock

- **Message time matches clock** (rule `message-time-matches-clock`, guard rule that denies a send_message whose header time is off the clock). Risk kind: incident. Incident: on 2026-11-07 the claude-settings coordinator stamped its send_message headers 10 to 25 minutes ahead of the clock, twice ("13:40 CST" sent at 13:22 CST, "13:50 CST" at 13:26 CST). A lane caught it. Harm: wrong times mislead triage's records, owner-ruling times and age-based checks.
  - Form: the header is the first non-blank line of a `mcp__claude-code-remote__send_message` message, after optional markdown lead characters. It starts with a label of one to four words, then `,`, `:` or a spaced dash (`-`, `—` or `–`), then the time. The time has an optional `YYYY-MM-DD`, a 1- or 2-digit hour, optional `:SS`, and CST or CDT in any letter case. Examples: `Coordinator, 13:28 CST: ...`, `Triage, 7:40 cst: ...` and `Now: 13:28 CST`. The guard judges that one stamp by its position. It guesses nothing from prose.
  - Verdict: deny when the zone name is wrong for the season, whatever the minutes (local_time's DST rule names the current zone, so `07:08 CDT` at 07:08 CST is refused). A dated stamp is refused when it is more than 1 minute ahead of the clock, with no upper limit. An undated stamp is refused only when it is 2 to 60 minutes ahead. It is read as a signed minute-of-day offset in [-720, 720), across midnight. One more than 60 minutes ahead is read as a quote from an earlier day, and passes. A stamp behind passes when its zone name is right (every incident was ahead; coordinator pick 2026-11-07 14:48 CST). The window and the wrong-zone refusal: lane pick 2026-11-08 07:14 CST. The refusal prints the real time.
  - Written times (step `stamp-check-page-and-roadmap`). Incident: on 2026-11-07 triage 6 wrote page item 364 with `added` `2026-11-07T20:16:00Z` at 20:14Z, and roadmap step `updatedAt` values ahead of the clock. It refuses a written ISO-8601 instant with an offset when it is more than 1 minute ahead of the clock, with no window. A value behind passes. Both sides are cut to the whole minute. The refusal prints the time in Central and in ISO form. It judges these values:
    - `added` in an ArtifactData write to collection `items`: set, update, each batch write, the document inline or through `file_path`, and a `str_replace` of `added`.
    - A `str_replace` whose new text is a time fragment, such as `T20:24:00Z`, is judged on the day that puts it nearest the clock. A behind fragment passes, and so does yesterday's late time after UTC midnight.
    - In `roadmap/data/steps/<name>.json`: `updatedAt` in a Write, and each instant in an Edit's or MultiEdit's new text, with or without a key. A step holds only past times.
    - In a Bash command: an `updatedAt` key with a double-quoted value after `:`, `=` or jq's `|=`. The key may be bare, quoted either way, or closed by `]`. A `==` or `>` compare passes. It judges only the last such literal, so a repair that rewrites an ahead value to the right time passes.
  - Passes: every other stamp, such as a quoted owner-ruling time later on the header line, a stamp on a later line, or a message with no header. Also a time in an items document's prose (`note`, `why`) or other field, another collection, a value with no offset, and `updatedAt=$T`, where the shell variable holds the value. An override lifts it.
  - Steer: the refusal names two fixes. Re-stamp your own header with the printed time. Or, if the first line quotes someone else's time in header form, open the message with your own label first. The clock is cut to the minute before the compare, so a dated stamp and an undated one judge the same.
  - Known miss: a label of 5 or more words, a stale stamp behind the clock, and an undated stamp more than 60 minutes ahead. Also a sender's time in any other form, such as `13:40 CST, coordinator here`, and commit messages (no incident). Also other page time fields such as `replied` and `ruled` (no incident). In a shell command: a single-quoted or unquoted `updatedAt` value, a jq `--arg` value, and a literal set in a shell variable first. Also a command whose ahead value is not its last `updatedAt` literal. In any written value: a space as the date separator, an hour-only offset such as `-06`, and a time fragment with no `T`. A bare time fragment in a step Edit, and a step file written through a GitHub tool (no incident). A str_replace fragment more than 12 hours ahead reads as behind.
  - Known false alarm, each costing one retry. For the first three, the refusal names the fix.
    - A quoted stamp in header form up to 60 minutes ahead, such as `Owner, 13:40 CST: ...` at 13:22 CST. Open with your own label instead.
    - A first line that names a future time 2 to 60 minutes ahead, such as `ETA: 07:45 CST` or `PR 12 merged - 07:40 CST deadline`. Move the time off the first line.
    - A dated quote from the other DST season, such as `Owner, 2026-10-30 16:20 CDT: grant` sent in winter. The wrong-zone check refuses it whatever the minutes. Open with your own label instead.
    - A Bash fixture with a deliberate future `updatedAt`, such as a `curl -d` body or a heredoc. Write it through the Write tool, or put the value in a shell variable.
    - A read-only grep for an `updatedAt` literal that is ahead of the clock. Put the value in a shell variable.
    - A step Edit whose prose or other field holds an instant ahead of the clock. Write the whole file with Write, which reads only `updatedAt`.
    - A fragment fix to an older item, to a time up to 12 hours later in the day than the clock. Example: yesterday's `T18:00Z` set to `T19:00Z` at 08:00Z. Write the whole value.
  - Cost: one clock read per send_message, and per ArtifactData, Write, Edit, MultiEdit or Bash call that carries a judged value, inside the guard process the PreToolUse matcher already starts. One local file read, only for an ArtifactData items write that carries `file_path` and no inline data. No transcript read, process or timer.
  - Tests: family `message-time-matches-clock` in `hooks/test_guard.py`.
