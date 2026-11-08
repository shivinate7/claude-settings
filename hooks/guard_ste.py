"""The ste-lint reads that bin/ste-changed and the guard's rule `ste-push` share, and the lint run the rule makes.

Nothing here runs on import, and no function exits: bin/ste-changed and hooks/guard_merge.py import it.
Standard library plus `_nowindow`; the pointer and config reads are imported when a call needs them.

  Scope      the `paths`, `exclude` and `changed_paths` defaults of actions/ste-lint/action.yml, with the pushed
             checkout's .ste-lint-exclude, as pathspecs that `git diff` reads the way actions/ste-lint/run.sh does.
  CI pin     a `<owner>/claude-settings/actions/ste-lint@<sha>` line in a workflow of the checkout.
  Lint       the program `<program> <base>`, run in the checkout, with a time limit, read by its verdict line.
"""
import os
import re
import signal
import subprocess
import sys

try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # install-hooks-whole: the guard set lands whole, the helper beside it a moment later; the guard still judges
    _nowindow = subprocess

LINT_ACTION = os.path.join("actions", "ste-lint", "action.yml")
LINT_INPUTS = ("paths", "exclude", "changed_paths", "decisions-dir")
EXCLUDE_FILE = ".ste-lint-exclude"
EXCLUDE_ENV = "STE_CHANGED_EXCLUDE"   # extra `exclude` pathspecs for bin/ste-changed: the pinned step's own `exclude` input
LINT_SECONDS = 40   # under the hook's own 60 s limit; measured 1.2 s for a small push, 7.6 s for 138 files
VERDICT = re.compile(r"^ste-lint: (PASS|FAIL),", re.M)
FINDING = re.compile(r"^::error file=([^,]*)(?:,line=(\d+))?::(.*)$", re.M)


def action_default(text, name):
    """The `default:` of input `name` in action.yml's text, or None when the input has none."""
    found = re.search(r"^  %s:.*?\n    default: \"([^\"]*)\"" % re.escape(name), text, re.M | re.S)
    return found.group(1) if found else None


def lint_inputs(text):
    """{input: default or None} for each input in LINT_INPUTS."""
    return {name: action_default(text, name) for name in LINT_INPUTS}


def find_checkout(own):
    """The claude-settings checkout that holds the lint step: `own`, else the clone the global CLAUDE.md
    names on its `@<dir>/CLAUDE.md` line, else ''. A copy install has no actions/ of its own."""
    if os.path.isfile(os.path.join(own, LINT_ACTION)):
        return own
    try:
        import guard_pointer  # the one reader of the pointer line (hooks/guard_pointer.py)
        pointed = guard_pointer.pointer_checkout()
    except Exception:
        pointed = ""
    return pointed if pointed and os.path.isfile(os.path.join(pointed, LINT_ACTION)) else ""


def own_checkout():
    """The checkout this file sits in, when it sits in one."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def pin_pattern(actions):
    """The regex of a pinned claude-settings action: group 1 the action, group 2 the commit."""
    return re.compile(r"[\w.-]+/claude-settings/actions/(%s)@([0-9a-f]{40})" % "|".join(map(re.escape, actions)))


def workflow_pins(top, pattern):
    """{(action, sha): first "file:line" that pins it}, from the workflows of the checkout at `top`."""
    found = {}
    folder = os.path.join(top, ".github", "workflows")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
        if name.endswith((".yml", ".yaml")):
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, 1):
                        for key in pattern.findall(line.split("#", 1)[0]):
                            found.setdefault(key, ".github/workflows/%s:%d" % (name, number))
            except OSError:
                continue
    return found


LINT_PIN = pin_pattern(("ste-lint",))


def ci_runs_lint(top):
    """True when CI of the checkout at `top` runs the ste-lint step: a workflow pins it, or the checkout is
    claude-settings itself, which holds the step."""
    return os.path.isfile(os.path.join(top, LINT_ACTION)) or bool(workflow_pins(top, LINT_PIN))


def scope_pathspecs(top, extra=""):
    """The pathspecs after `--` in `git diff --name-only <range> --`, read from `top`, that select the files
    the lint step lints: `changed_paths`, then one `:(exclude,glob)` for each line of .ste-lint-exclude, each
    item of the `exclude` default and each item of `extra` (the pinned step's `exclude` input). None when
    action.yml or its defaults cannot be read."""
    root = find_checkout(own_checkout())
    try:
        with open(os.path.join(root, LINT_ACTION), encoding="utf-8") as handle:
            inputs = lint_inputs(handle.read())
    except OSError:
        return None
    if inputs["changed_paths"] is None or inputs["exclude"] is None:
        return None
    lines = []
    try:
        with open(os.path.join(top, EXCLUDE_FILE), encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        pass
    lines += (inputs["exclude"] + "\n" + extra).replace(",", "\n").splitlines()
    patterns = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return [inputs["changed_paths"]] + [":(exclude,glob)" + pattern for pattern in patterns]


def _unquoted(value):
    value = value.strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"" else value


def pinned_with(top):
    """{input: unquoted value} of the `with:` block of the first workflow step of the checkout at `top` that
    pins the ste-lint action, {} when that step has none or no step pins it. The step reader is
    lint/workflow_steps.py, beside this folder. Raises when it cannot be read."""
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import workflow_steps
    folder = os.path.join(top, ".github", "workflows")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        for step in workflow_steps.step_blocks(text):
            if LINT_PIN.search((workflow_steps.step_key(step, "uses") or "").split("#", 1)[0]):
                return {key: _unquoted(value) for key, value in workflow_steps.step_with(step).items()}
    return {}


def pinned_plan(top):
    """(state, exclude, why) for the pinned step's `with:` inputs, as CI applies them. state is "lint" (run the
    lint; `exclude` holds the step's own `exclude` input to apply), "off" (`fail: false`: the step reports and
    never fails, so no lint is needed) or "unknown" (an input this guard does not apply, or a read that failed:
    `why` says which). An input at the action's default is no input; a `${{ }}` expression is not evaluated."""
    try:
        given = pinned_with(top)
        with open(os.path.join(find_checkout(own_checkout()), LINT_ACTION), encoding="utf-8") as handle:
            action = handle.read()
    except Exception as err:
        return "unknown", "", "the pinned step's inputs could not be read (%s)" % type(err).__name__
    for name, value in given.items():
        if "${{" in value:
            return "unknown", "", "the pinned input %s is an expression the guard cannot evaluate" % name
    if given.get("fail", "").lower() == "false":
        return "off", "", ""
    exclude = ""
    for name, value in given.items():
        if value == action_default(action, name) or (name == "fail" and value.lower() == "true"):
            continue
        if name == "exclude":
            exclude = value
            continue
        return "unknown", "", "the pinned input %s: %s is one the guard does not apply" % (name, value or "empty")
    return "lint", exclude, ""


def program_path(top):
    """The lint program: STE_CHANGED_BIN, else bin/ste-changed of the installed config folder, else of the
    claude-settings checkout. '' when none is a file."""
    named = os.environ.get("STE_CHANGED_BIN")
    if named:
        return named if os.path.isfile(named) else ""
    from shared_names import config_dir
    for folder in (config_dir(), find_checkout(own_checkout())):
        path = os.path.join(folder, "bin", "ste-changed") if folder else ""
        if path and os.path.isfile(path):
            return path
    return ""


def _argv(program, base):
    runnable = program.lower().endswith((".cmd", ".bat", ".exe")) or (os.name != "nt" and os.access(program, os.X_OK))
    return ([program] if runnable else [sys.executable, program]) + [base]


def _kill_tree(proc):
    """Stop the lint child and what it started. The child leads its own process group, so the group is ours."""
    try:
        if os.name == "nt":
            _nowindow.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_lint(program, base, top, seconds=None, exclude=""):
    """((exit code, stdout, stderr), '') after the lint ran in `top`, else (None, why). A lint past its time
    limit is killed with its children and reads as no result. `exclude` reaches the program as EXCLUDE_ENV."""
    seconds = LINT_SECONDS if seconds is None else seconds
    env = dict(os.environ, **{EXCLUDE_ENV: exclude})
    try:
        proc = _nowindow.Popen(_argv(program, base), cwd=top, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                               start_new_session=os.name != "nt", env=env)
    except OSError as err:
        return None, "the lint program did not start (%s)" % (err.strerror or type(err).__name__)
    try:
        out, err = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return None, "the lint ran past %d s" % seconds
    return (proc.returncode, out or "", err or ""), ""


def verdict_of(out):
    """'PASS' or 'FAIL' from the last `ste-lint: PASS|FAIL,` line of the step's stdout, else ''."""
    found = VERDICT.findall(out)
    return found[-1] if found else ""


def _unescape(text):
    """Undo GitHub workflow-command escaping (actions/ste-lint/run.sh `_esc`)."""
    for coded, plain in (("%0A", "\n"), ("%0D", "\r"), ("%3A", ":"), ("%2C", ","), ("%25", "%")):
        text = text.replace(coded, plain)
    return text


def error_findings(out, limit=3):
    """[(file, line or '', "STE001 message")] for the first `limit` error findings the step printed."""
    rows = []
    for path, line, text in FINDING.findall(out):
        rows.append((_unescape(path), line, _unescape(text).strip()))
        if len(rows) == limit:
            break
    return rows

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
