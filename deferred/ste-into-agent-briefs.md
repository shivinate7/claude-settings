# The STE writing standard moves into agent briefs

**What waits.** Move the STE writing standard out of `CLAUDE.md` and into agent briefs, as a writing standard. Today `CLAUDE.md` holds one line, rule `output-write-in-ste`. The six advisory rules of the lint are a stand-in nudge. `agents/*.md` still say "Write in Simplified Technical English".

**Why it waits.** Owner ruling 2026-10-17 (`plain-prose-lint`, the STE lint becomes a plain-prose lint): the advisory nudge is "only temporary". The orchestrator left `agents/*.md` as they are, because agent briefs are the future home of the standard. The move needs a decision on what the briefs hold and what the lint keeps.

**What keeps it from being lost.** This file.

**Trigger.** The owner's word, or when the advisory nudge has run 30 days, whichever comes first. The 30 days start when the plain-prose lint merges to main. Count them by date: the nudge writes no log line (debt `advisory-note-not-logged`).
