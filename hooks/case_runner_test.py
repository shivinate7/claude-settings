"""The case runner that hooks/test_stall_watch.py and hooks/test_stall_watch_stop.py share.
Standard library only. It holds no case and runs nothing: a test file imports it.

It is not a test_*.py file because it has no suite of its own, so it has no CI step.
"""


class Skip(Exception):
    """A case raises it when this host cannot run the case. It prints as SKIP and never fails the run."""


def no_cases_exit(cases, runner):
    """Return 1 and print a line saying no cases ran when a runner's case list is empty, else None.
    A runner calls it first, so a list emptied by mistake fails the run. A skipped case is a case that
    ran, so a list of skips is not empty."""
    if cases:
        return None
    print(f"{runner} FAIL: no cases ran, so nothing was checked")
    return 1


def run_cases(cases, failures=None, echo_pass=True):
    """Run each case function. A case returns a list of problems, empty for a pass.
    A case that raises or calls sys.exit is a failed case. Return 1 when any case failed, or when there are no cases, else 0.

    failures: an optional list that a suite's checks append to when they fail. A case that adds
    to it fails with those entries as its problems, even when it returns nothing. A case that
    raises or returns problems is appended to it, so the suite's own count sees the failure.
    echo_pass: False prints no PASS line for a passing case; FAIL lines and the summary still print."""
    if no_cases_exit(cases, "run_cases"):
        return 1
    failed = skipped = 0
    for fn in cases:
        name = (fn.__doc__ or fn.__name__).strip()
        before = len(failures) if failures is not None else 0
        try:
            problems = fn()
        except Skip as s:
            skipped += 1
            print(f"SKIP {name}: {s}")
            continue
        except SystemExit as e:  # a case that exits is a failed case, named; the run goes on (KeyboardInterrupt still stops it)
            problems = ["the case called sys.exit(%r)" % (e.code,)]
        except Exception as e:  # a missing module or a crash is a failed case, not a stop
            problems = [str(e)]
        grew = failures is not None and len(failures) > before
        if grew and not problems:
            problems = failures[before:]
        elif failures is not None and problems and not grew:
            failures.append(name)
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"  - {p}")
        elif echo_pass:
            print(f"PASS {name}")
    print(f"{len(cases)} cases, {failed} failed, {skipped} skipped")
    return 1 if failed else 0
