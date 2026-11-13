"""The one home of an append to the stall watch's beat file ($STALL_WATCH_BEAT, named by hooks/stall_watch.py).
Standard library only, so bin/verdict and bin/ci-job import it at no cost. A beat is written when a tool has
something to say. ci-job's `start:` line is written once per step, as the step starts, never on a timer, so a step that has started and then says nothing adds no more bytes. verdict's heartbeat, which also uses this module, is timed."""
import os


def beat(line):
    """Append line and a newline to the file $STALL_WATCH_BEAT names, when set and non-empty. An OSError is
    ignored: a gone beat file must not fail a check."""
    path = os.environ.get("STALL_WATCH_BEAT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
