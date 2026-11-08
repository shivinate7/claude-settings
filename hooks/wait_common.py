"""One home for the parts that bin/wait-pid and bin/wait-until share: the exit-2 refusal of a bad
argument, the number parse, the `[--timeout SECS]` argument loop, the heartbeat interval and the poll loop.

Why one home: both helpers wait for a condition with no process of their own to hold, print a line every
heartbeat so a quiet background run does not trip the stall watch (300 s quiet), and end with the same exit
codes: 0 done, 124 at --timeout, 2 a bad argument. The default --timeout differs by helper
(DEFAULT_TIMEOUTS). Cost per wait: one process, a wake every poll seconds (POLL by default), no file written.
"""
import os
import re
import sys
import time

# Seconds a helper waits when it gets no --timeout; 0 means no cap. wait-pid caps at 540, under Bash's 600 s,
# because the pid it waits on may never end. wait-until has no cap: its target time ends the wait.
DEFAULT_TIMEOUTS = {"wait-pid": 540.0, "wait-until": 0.0}
CAPPED = 540.0  # the default for a helper the table does not name
HEARTBEAT_DEFAULT = 120.0
POLL = 0.25  # the default seconds between polls
EXIT_TIMEOUT = 124


def die(prog, message):
    """Print `prog: message` to stderr and exit 2."""
    print("%s: %s" % (prog, message), file=sys.stderr)
    sys.exit(2)


def number(prog, usage, text, name):
    """`text` as a finite number of at least 0, else exit 2."""
    try:
        value = float(text)
    except ValueError:
        value = -1.0
    if value < 0 or value != value or value == float("inf"):
        die(prog, "bad %s %r. %s" % (name, text, usage))
    return value


def split_args(prog, usage, argv):
    """(the one positional argument or None, the timeout) from `[ARG] [--timeout SECS]`, exit 2 on any
    other argument. A leading `-` is no flag unless it starts `--`, so a negative number is a positional."""
    positional, timeout = None, DEFAULT_TIMEOUTS.get(prog, CAPPED)
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--timeout" and args:
            timeout = number(prog, usage, args.pop(0), "timeout")
        elif arg.startswith("--timeout="):
            timeout = number(prog, usage, arg[len("--timeout="):], "timeout")
        elif positional is None and not re.match(r"--", arg):
            positional = arg
        else:
            die(prog, "bad argument %r. %s" % (arg, usage))
    return positional, timeout


def heartbeat_seconds(variable):
    """Seconds between heartbeat lines: the number in env var `variable`, else HEARTBEAT_DEFAULT."""
    try:
        beat = float(os.environ.get(variable) or HEARTBEAT_DEFAULT)
    except ValueError:
        beat = HEARTBEAT_DEFAULT
    return beat if beat > 0 else HEARTBEAT_DEFAULT


def wait_loop(prog, step, timeout, beat, still_text, timeout_text, poll=POLL):
    """Poll `step(elapsed)` every `poll` seconds until it returns an exit code, which this returns.
    `step` prints its own end line. At `timeout` seconds (0 means no cap) print `timeout_text(elapsed)` and
    return 124. Every `beat` seconds print `still_text(elapsed)`. Each line starts `prog: `."""
    start = time.monotonic()
    next_beat = start + beat
    while True:
        time.sleep(poll)
        now = time.monotonic()
        code = step(now - start)
        if code is not None:
            return code
        if timeout and now - start >= timeout:
            print("%s: %s" % (prog, timeout_text(now - start)), flush=True)
            return EXIT_TIMEOUT
        if now >= next_beat:
            print("%s: %s" % (prog, still_text(now - start)), flush=True)
            next_beat = now + beat
