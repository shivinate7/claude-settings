# section 35555
FAMILY = _section_family


# Judge's CPU time (1 s), not wall-clock (flaky on macOS runners), bounds a run of apostrophes; a 30 s kill guard stops a hang.
APOSTROPHE_CHILD = r'''
import contextlib, importlib.util, io, json, os, sys, time
hooks = sys.argv[1]
sys.path.insert(0, hooks)
spec = importlib.util.spec_from_file_location("guard_under_test", os.path.join(hooks, "guard.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
payload = json.load(sys.stdin)
printed = io.StringIO()
started = time.process_time()
try:
    with contextlib.redirect_stdout(printed):
        mod.judge(payload)
except SystemExit:
    pass
print(json.dumps({"cpu": time.process_time() - started, "out": printed.getvalue()}))
'''


def _apostrophe_speed_case(command):
    def check():
        materialize(NOGIT)
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": NOGIT}
        try:
            done = subprocess.run(
                [sys.executable, "-c", APOSTROPHE_CHILD, os.path.dirname(GUARD)],
                input=json.dumps(payload), capture_output=True, text=True, timeout=30,
                env=dict(os.environ, CLAUDE_CONFIG_DIR=CFG),
            )
        except subprocess.TimeoutExpired:
            return False, "not judged within 30 s, killed; the bound is 1 s of CPU"
        reply = json.loads(done.stdout.strip())
        took = reply["cpu"]
        if took >= 1.0:
            return False, "judged in %.2f s CPU, not under 1 s" % took
        got = "allow" if not reply["out"].strip() else \
            json.loads(reply["out"])["hookSpecificOutput"]["permissionDecision"]
        return True, "judged %s in %.2f s CPU, under 1 s" % (got, took)
    return check


for _name, _command in (
    ("a run of lone apostrophes", "echo " + "don't " * 60),
    ("a run of contraction pairs", "a's b'; " * 50),
):
    LOG_CHECKS_EXTRA.append(("guard-command-position: speed, %s, judged in under 1 s CPU" % _name,
                             _apostrophe_speed_case(_command)))


# Ruling item 4: _split_segments_cached is keyed on the command alone, but split_segments reads
# POWERSHELL_CALL[0] too. A POSIX backslash-newline is a continuation, and PowerShell ends the
# segment there, so one text splits two ways. A split made under one flag must not be served to the
# other.
def split_cache_power_shell_case():
    guard = _load_guard_module()
    text = "echo a\\\nb; ls"
    try:
        guard.POWERSHELL_CALL[0] = False
        posix = guard.split_segments(text)
        guard.POWERSHELL_CALL[0] = True
        cached = guard.split_segments(text)
        direct = guard.split_segments(text, [])   # the uncached path: the oracle for this flag
    finally:
        guard.POWERSHELL_CALL[0] = False
    if direct == posix:
        return False, "the two flags split alike, so the case proves nothing: %r" % (direct,)
    if cached != direct:
        return False, "PowerShell split served from the POSIX cache: got %r, want %r" % (
            cached, direct)
    return True, "PowerShell split %r differs from the POSIX split %r" % (direct, posix)


LOG_CHECKS_EXTRA.append(("split cache: the PowerShell flag is part of the split, not only the command",
                         split_cache_power_shell_case))


# --------------------------------------------------------------------------- fail-closed
#
# audit-high (decision guard-hooks-fail-closed): a guard
# whose sibling module is missing refuses the call. guard.py allows instead, and 121 guard-crash
# lines on 2026-10-13 (12:03 to 12:44) ran with every guard off. A case copies guard.py and its
# guard_* siblings into a scratch folder, deletes one sibling, and runs a plain Bash call. The control
# is an intact copy's deny, so the exit code is read from a real refusal, never assumed.
