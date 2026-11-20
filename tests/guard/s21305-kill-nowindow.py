# section 21305
# Loads after s21304-diff.py, which creates LOG_CHECKS_EXTRA. Its one check reads the process tree
# that a kill walks, so it belongs to the kill family.
FAMILY = "kill"


def nowindow_descendants_case():
    """descendants() reads the process table of the platform (Linux /proc, else `ps -A`, the darwin arm).
    The parent is a Python child that starts a `sleep` and prints its pid. descendants(parent) must hold it."""
    if os.name == "nt":
        return SKIP, "Windows reads no process table in descendants, so it returns [] and this check does not run"
    import _nowindow
    code = ("import subprocess, time\n"
            "child = subprocess.Popen(['sleep', '300'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(300)\n")
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True)
    grandchild, found = None, []
    try:
        grandchild = int(parent.stdout.readline())
        found = _nowindow.descendants(parent.pid)
    except ValueError:
        return False, "the parent printed no grandchild pid, so there is no tree to read"
    finally:
        parent.kill()
        parent.wait()
        if grandchild is not None:
            try:
                os.kill(grandchild, signal.SIGKILL)
            except OSError:
                pass
    if grandchild not in found:
        return False, "descendants(%d) does not hold its grandchild %d: got %s" % (parent.pid, grandchild, found)
    return True, "descendants finds the grandchild of a live parent in the platform's process table"


LOG_CHECKS_EXTRA.append(("kill: descendants finds the grandchild of a live parent, through the platform's "
                         "process table reader", nowindow_descendants_case))
