# section 43820
# A family module (a name in guard._FAMILY_MODULES) may define hit(call) and shell_hit(call). judge calls hit for each
# family module that defines it, after judge's own tool rules and before its tool-specific tail. judge_shell calls
# shell_hit after its own rules and before settle_ask. Neither runs for a Read, a Grep or a SubagentStop. A hit refuses
# by calling guard_core.refuse with its own literal rule id; returning passes. A raise inside hit takes main()'s
# fail-open path, with one guard-crash line in guard.log. Each run goes through a probe script, so the hook's own stdout
# and guard.log are what the cases read, as Claude Code reads them.
FAMILY = "family-hit"  # the cases after this section keep family-hit's family

FH_DIR = os.path.join(ROOT, "family-hit")          # this family's folder under the run folder
FH_PLAIN = os.path.join(FH_DIR, "plain")           # a folder with no git repo: every call here is judged in it
FH_NOTE = os.path.join(FH_PLAIN, "note.txt")       # the path a Write names
FH_PROBE = os.path.join(FH_DIR, "hook_probe.py")   # runs guard.main() with the family hits that FH_ATTACH names
os.makedirs(FH_PLAIN, exist_ok=True)

# The probe loads the guard under test, sets each (module, attr, mode) of FH_ATTACH on its family module, and runs main().
# A mode is "record" (the hit notes the call and passes), "refuse" (the hit refuses with rule family-hit-fake) or
# "raise" (the hit raises). The notes go to FH_SIDE when the run ends, whichever way it ends.
FH_PROBE_TEXT = """\
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location("guard_under_test", %(guard)r)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
seen = []


def make_hit(module, attr, mode):
    def fake(call):
        row = {"module": module, "attr": attr, "tool": getattr(call, "tool", "<no tool>")}
        for field in ("raw", "stripped", "cmd"):
            if hasattr(call, field):
                row[field] = getattr(call, field)
        seen.append(row)
        if mode == "refuse":
            sys.modules["guard_core"].refuse(row["tool"], "deny", "family-hit-fake",
                                            "the probe refused this call", "probe")
        if mode == "raise":
            raise RuntimeError("family-hit probe raised")
    return fake


try:
    for module, attr, mode in json.loads(os.environ.get("FH_ATTACH", "[]")):
        setattr(sys.modules[module], attr, make_hit(module, attr, mode))
    guard.main()
finally:
    with open(os.environ["FH_SIDE"], "w", encoding="utf-8") as handle:
        json.dump(seen, handle, default=repr)
"""
with open(FH_PROBE, "w", encoding="utf-8") as handle:
    handle.write(FH_PROBE_TEXT % {"guard": os.path.abspath(GUARD)})


def fh_run(name, tool, tool_input, attach, event=None):
    """One guard run of one call through the probe, with `attach` set on the family modules first. Returns
    (decision, reason, hit rows, guard-crash lines). The run's folder is its own config folder, so its guard.log
    and its side file are read from there."""
    run = os.path.join(FH_DIR, "run-" + name)
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    side = os.path.join(run, "calls.json")
    # A "raise" attach mode raises on purpose, so its one guard-crash line is expected: only such a run declares crash.
    raises = any(mode == "raise" for _, _, mode in attach)
    case = {"raw": None, "tool": tool, "tool_input": tool_input, "cwd": FH_PLAIN, "session": None,
            "env_path": None, "config": run, "event": event, "guard": FH_PROBE, "crash": raises,
            "env": {"FH_SIDE": side, "FH_ATTACH": json.dumps(attach)}}
    got, reason = decide(case)
    rows = []
    if os.path.exists(side):
        with open(side, encoding="utf-8") as handle:
            rows = json.load(handle)
    crashes = [line for line in (_session_log_rows(run) or []) if line.split("\t")[2:4] == ["crash", "guard-crash"]]
    return got, reason, rows, crashes


def fh_trail(rows):
    """(module, attr, tool) of each hit row, in the order the guard called them."""
    return [(row.get("module"), row.get("attr"), row.get("tool")) for row in rows]


def fh_write_input():
    return {"file_path": FH_NOTE, "content": "family-hit\n"}


def fh_family_order():
    """The names in guard._FAMILY_MODULES, read with the ast: the guard is judged as the file on disk, not as imported here."""
    with open(GUARD, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=GUARD)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_FAMILY_MODULES" for t in node.targets):
            if isinstance(node.value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in node.value.elts):
                return tuple(e.value for e in node.value.elts)
    return None


def fh_hit_for_write_and_bash_check():
    """hit runs once for a Write and once for a Bash call, in the order the guard judges them."""
    attach = [("guard_wsl", "hit", "record")]
    _, _, write_rows, _ = fh_run("hit-write", "Write", fh_write_input(), attach)
    _, _, bash_rows, _ = fh_run("hit-bash", "Bash", {"command": "echo family-hit"}, attach)
    want = [("guard_wsl", "hit", "Write"), ("guard_wsl", "hit", "Bash")]
    got = fh_trail(write_rows) + fh_trail(bash_rows)
    if got != want:
        return False, "hit calls were %r, want %r" % (got, want)
    return True, "hit ran once for the Write and once for the Bash call"


def fh_hit_refusal_is_output_check():
    """A refusal that hit makes through guard_core.refuse is the hook's output: a deny that prints the hit's rule."""
    got, reason, _, _ = fh_run("hit-refuse", "Write", fh_write_input(), [("guard_wsl", "hit", "refuse")])
    if got != "deny":
        return False, "decision %s, want deny: %s" % (got, reason[:100])
    if printed_rule(reason) != "family-hit-fake":
        return False, "the reason prints rule %r, want family-hit-fake" % printed_rule(reason)
    return True, "the hit's refusal is the hook's deny, with its rule"


def fh_shell_hit_for_bash_check():
    """shell_hit runs once for a Bash call, with raw, stripped and cmd set, and never for a Write."""
    attach = [("guard_wsl", "shell_hit", "record")]
    _, _, bash_rows, _ = fh_run("shell-bash", "Bash", {"command": "echo family-hit"}, attach)
    _, _, write_rows, _ = fh_run("shell-write", "Write", fh_write_input(), attach)
    want = [("guard_wsl", "shell_hit", "Bash")]
    if fh_trail(bash_rows) != want:
        return False, "shell_hit calls for the Bash call were %r, want %r" % (fh_trail(bash_rows), want)
    row = bash_rows[0]
    if row.get("raw") != "echo family-hit":
        return False, "raw on the shell_hit call is %r, want the command as typed" % (row.get("raw"),)
    for field in ("stripped", "cmd"):
        if row.get(field) in (None, ""):
            return False, "%s is not set on the shell_hit call" % field
    if write_rows:
        return False, "shell_hit ran for a Write: %r" % (fh_trail(write_rows),)
    return True, "shell_hit ran once for the Bash call, with raw, stripped and cmd set, and not for the Write"


def fh_no_hit_for_read_grep_or_stop_check():
    """Neither function runs for a Read, a Grep or a SubagentStop. The Write run beside them must reach hit, so the
    check is not green on a guard that calls nothing."""
    attach = [("guard_wsl", "hit", "record"), ("guard_wsl", "shell_hit", "record")]
    read_got, _, read_rows, _ = fh_run("no-read", "Read", {"file_path": FH_NOTE}, attach)
    grep_got, _, grep_rows, _ = fh_run("no-grep", "Grep", {"pattern": "family-hit", "path": FH_PLAIN}, attach)
    stop_got, _, stop_rows, _ = fh_run("no-stop", "Bash", {"command": "echo family-hit"}, attach, event="SubagentStop")
    _, _, write_rows, _ = fh_run("no-write", "Write", fh_write_input(), attach)
    for label, got, rows in (("a Read", read_got, read_rows), ("a Grep", grep_got, grep_rows),
                             ("a SubagentStop", stop_got, stop_rows)):
        if got != "allow":
            return False, "%s: decision %s, want allow with no refusal" % (label, got)
        if rows:
            return False, "a hit ran for %s: %r" % (label, fh_trail(rows))
    want = [("guard_wsl", "hit", "Write")]
    if fh_trail(write_rows) != want:
        return False, "the Write's calls were %r, want %r" % (fh_trail(write_rows), want)
    return True, "no hit for a Read, a Grep or a SubagentStop, and the Write reached hit alone"


def fh_module_without_functions_check():
    """A family module with neither function passes the call: no decision, no reason and no guard-crash line. The
    other module's hit still runs. guard_mask_script gets no attribute in this run, as in the repo's copy."""
    attach = [("guard_wsl", "hit", "record")]
    got, reason, rows, crashes = fh_run("no-functions", "Write", fh_write_input(), attach)
    if crashes:
        return False, "a guard-crash line was written: %r" % (crashes[0].split("\t")[4:5],)
    if got != "allow" or reason:
        return False, "decision %s, reason %r, want an allow with no reason" % (got, reason[:100])
    want = [("guard_wsl", "hit", "Write")]
    if fh_trail(rows) != want:
        return False, "hit calls were %r, want %r" % (fh_trail(rows), want)
    return True, "the call is allowed with no crash line, and the other module's hit ran"


def fh_family_order_check():
    """Two modules' hits run in the order _FAMILY_MODULES lists them, whatever order they were attached in."""
    order = fh_family_order()
    if order is None:
        return False, "guard.py has no _FAMILY_MODULES tuple of string names to read the order from"
    pair = ("guard_stream", "guard_rm_var")
    if not all(name in order for name in pair):
        return False, "%r is not in _FAMILY_MODULES" % (pair,)
    want_names = sorted(pair, key=order.index)
    if want_names == sorted(pair):
        return False, "the pair runs in name order as well, so it cannot tell list order from name order"
    attach = [("guard_rm_var", "hit", "record"), ("guard_stream", "hit", "record")]
    _, _, rows, _ = fh_run("order", "Write", fh_write_input(), attach)
    want = [(name, "hit", "Write") for name in want_names]
    if fh_trail(rows) != want:
        return False, "hit calls were %r, want %r in _FAMILY_MODULES order" % (fh_trail(rows), want)
    return True, "hit ran in _FAMILY_MODULES order: %s" % ", ".join(want_names)


def fh_earlier_refusal_wins_check():
    """An earlier refusal stands and shell_hit never runs for it: `pkill -f node` is refused by an existing rule before
    shell_hit. A Bash call no earlier rule refuses reaches shell_hit, whose refusal is then the hook's output."""
    attach = [("guard_wsl", "shell_hit", "refuse")]
    got, reason, rows, _ = fh_run("earlier-refusal", "Bash", {"command": "pkill -f node"}, attach)
    if got != "deny":
        return False, "pkill -f node: decision %s, want the earlier rule's deny: %s" % (got, reason[:100])
    if printed_rule(reason) != "machine-wide-kill":
        return False, "pkill -f node: the printed rule is %r, want machine-wide-kill" % (printed_rule(reason),)
    if rows:
        return False, "shell_hit ran for a call an earlier rule refuses: %r" % (fh_trail(rows),)
    got, reason, _, _ = fh_run("sibling-refused", "Bash", {"command": "echo family-hit"}, attach)
    if got != "deny" or printed_rule(reason) != "family-hit-fake":
        return False, "echo family-hit: decision %s, rule %r, want the hit's deny (family-hit-fake)" % (
            got, printed_rule(reason))
    return True, "the earlier rule's deny stands with no shell_hit call, and the hit refuses a call no earlier rule refuses"


def fh_raising_hit_fails_open_check():
    """A raise inside hit takes main()'s fail-open path: the call is allowed and guard.log holds one guard-crash line
    that names the raise."""
    got, reason, _, crashes = fh_run("raise", "Write", fh_write_input(), [("guard_wsl", "hit", "raise")])
    if got != "allow":
        return False, "decision %s, want allow (a raise fails open): %s" % (got, reason[:100])
    if len(crashes) != 1:
        return False, "guard.log holds %d guard-crash lines, want 1" % len(crashes)
    matched = crashes[0].split("\t")[4] if len(crashes[0].split("\t")) > 4 else ""
    if "family-hit probe raised" not in matched:
        return False, "the guard-crash line does not name the raise: %r" % matched[:100]
    return True, "the call is allowed, and one guard-crash line names the raise"


def fh_hit_for_skill_check():
    """hit runs for a Skill call before judge's Skill tail, so a Skill no rule names is allowed after hit ran, and a hit
    refusal on a Skill call is the hook's deny."""
    attach = [("guard_wsl", "hit", "record")]
    got, reason, rows, _ = fh_run("hit-skill", "Skill", {"skill": "family-hit"}, attach)
    if got != "allow":
        return False, "decision %s, want allow for a Skill no rule names: %s" % (got, reason[:100])
    want = [("guard_wsl", "hit", "Skill")]
    if fh_trail(rows) != want:
        return False, "hit calls for a Skill call were %r, want %r" % (fh_trail(rows), want)
    got, reason, _, _ = fh_run("hit-skill-refused", "Skill", {"skill": "family-hit"}, [("guard_wsl", "hit", "refuse")])
    if got != "deny" or printed_rule(reason) != "family-hit-fake":
        return False, "a hit refusal on a Skill call: decision %s, rule %r, want the hit's deny (family-hit-fake)" % (
            got, printed_rule(reason))
    return True, "hit runs for a Skill call before its tail, and a hit refusal on it is the hook's deny"


FH_CAP_WRITE = "echo CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5 > settings.local.json"  # a settings write: holds an agent-model-cap ask


def fh_shell_hit_beats_held_ask_check():
    """A settings write holds the agent-model-cap ask until the other rules have run. shell_hit runs before settle_ask, so
    its refusal is the deny and the ask is never printed. The control beside it, with shell_hit passing, still asks."""
    got, reason, _, _ = fh_run("shell-ask-control", "Bash", {"command": FH_CAP_WRITE},
                               [("guard_wsl", "shell_hit", "record")])
    if got != "ask" or printed_rule(reason) != "agent-model-cap":
        return False, "control: decision %s, rule %r, want the held ask agent-model-cap" % (got, printed_rule(reason))
    got, reason, rows, _ = fh_run("shell-ask-refused", "Bash", {"command": FH_CAP_WRITE},
                                  [("guard_wsl", "shell_hit", "refuse")])
    if got != "deny" or printed_rule(reason) != "family-hit-fake":
        return False, "decision %s, rule %r, want shell_hit's deny (family-hit-fake) over the held ask" % (
            got, printed_rule(reason))
    want = [("guard_wsl", "shell_hit", "Bash")]
    if fh_trail(rows) != want:
        return False, "shell_hit calls were %r, want %r" % (fh_trail(rows), want)
    return True, "shell_hit's refusal beats the held agent-model-cap ask, and the same call asks when shell_hit passes"


FH_CHECKS = (
    ("family-hit: hit runs once for a Write and once for a Bash call, in that order", fh_hit_for_write_and_bash_check),
    ("family-hit: a hit refusal is the hook's deny, with the hit's rule", fh_hit_refusal_is_output_check),
    ("family-hit: shell_hit runs for a Bash call with raw, stripped and cmd set, and not for a Write",
     fh_shell_hit_for_bash_check),
    ("family-hit: neither function runs for a Read, a Grep or a SubagentStop",
     fh_no_hit_for_read_grep_or_stop_check),
    ("family-hit: a module with neither function passes, and another module's hit still runs",
     fh_module_without_functions_check),
    ("family-hit: two modules' hits run in _FAMILY_MODULES order, not attach order", fh_family_order_check),
    ("family-hit: an earlier refusal wins over shell_hit, and shell_hit refuses a call no earlier rule refuses",
     fh_earlier_refusal_wins_check),
    ("family-hit: a raising hit fails open with one guard-crash line", fh_raising_hit_fails_open_check),
    ("family-hit: hit runs for a Skill call before its tail, and a hit refusal on it is the deny",
     fh_hit_for_skill_check),
    ("family-hit: shell_hit's refusal beats a held settings-write ask, and the ask stays when shell_hit passes",
     fh_shell_hit_beats_held_ask_check),
)
for _label, _check in FH_CHECKS:
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
    LOG_FAMILY[_label] = "family-hit"
    FIXTURELESS_CHECKS.add(_check)  # each run builds its own folders and reads no lazy fixture
