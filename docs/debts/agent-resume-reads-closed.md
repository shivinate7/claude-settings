# An agent resumed after it closed is never listed

**What.** A TaskStop, or a terminal notice without the waiting text, closes an agent id for the whole transcript, so the Stop check drops every later launch under that id. An agent resumed under its id after that close is never listed, even when it goes quiet. The age rule never blocks it either, even past `AGENT_LONG`. The row's own remedy (stop it, then resume it by name) leads into this case, so Claude hits it in normal work.

**Where.** `hooks/stall_watch.py`, `scan_jobs`: `done` holds the closed ids for the whole transcript, and `scan_jobs` drops every id in it. `closed_by_notice` keeps a waiting notice open in the Stop check only.

**Decision.** stall-watch (a stalled background command is reported, never stopped; an agent past its age blocks a Stop until a check-in names it, once per run of Stops).

**Retire.** An agent closes only by a notice or TaskStop newer than its latest launch or SendMessage resume record. A resumed agent that goes quiet is listed, and a closed agent with no resume stays unlisted. A case in `hooks/test_stall_watch_stop.py` shows both: a TaskStop, a resume under the same id, and a quiet transcript. That case is not written yet.
