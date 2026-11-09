#!/usr/bin/env python3
"""Fails when a product file in hooks/ or lint/ needs a newer Python than the 3.9 floor.

README.md and lint/ste_lint.py state a floor of Python 3.9 for the guards and the lint. CI runs 3.11, so a
3.10+ call passes CI and crashes a guard on a 3.9 install, where the guard fails open. The incident:
`glob.iglob(root_dir=...)` (3.10). This check runs vermin (`-t=3.9-`, `--eval-annotations`) over the product files,
so a newer feature fails the run that adds it. vermin reads the source with the host's `ast`, so the host Python
must be 3.9 or newer.

A product file is a .py file under hooks/ or lint/ that is not a test: a path `is_test_rel` (hooks/guard.py, the
one home of what a test path is) calls a test, or a name `_test*.py`. A `# novermin` line comment excuses its
line, as vermin's marker does; the same text in a string does not. Use it on an import that a try/except
ImportError guards.

    python3 lint/check_python_floor.py [--root DIR]

DIR holds hooks/ and lint/ and defaults to the repo root. Needs vermin (`pip install vermin==1.9.2`). The vermin
command defaults to this Python running vermin's `main`; env FLOOR_VERMIN_CMD overrides it (split like a shell line).

Exits 0 and prints nothing when clean. Exits 1 and prints one line per offending file, naming the file and the
feature. Exits 2, naming the cause, when vermin cannot run, a product file cannot be read, or vermin cannot parse a
file: an unread file is never clean.
"""
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)

FOLDERS = ("hooks", "lint")
TARGET = "3.9-"
# vermin 1.9.2 ships no __main__, so `python -m vermin` fails; its console script runs main() like this.
DEFAULT_CMD = [sys.executable, "-c", "import sys; from vermin import main; sys.exit(main())"]
FLAGS = ["-t=" + TARGET, "--eval-annotations", "--no-tips", "--violations", "--quiet", "--no-make-paths-absolute"]
CHUNK = 100  # files per vermin run, so a Windows command line stays short
TIMEOUT = 300


class Unreadable(Exception):
    """vermin could not run, or a file could not be read: exit 2."""


def product_files(root):
    """Relative paths (with /) of the product .py files under root/hooks and root/lint, sorted."""
    found = []
    for folder in FOLDERS:
        top = os.path.join(root, folder)
        if not os.path.isdir(top):
            raise Unreadable("%s is not a folder" % top)
        for base, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            for name in names:
                if not name.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/")
                if guard.is_test_rel(rel) or name.startswith("_test"):
                    continue
                found.append(rel)
    return sorted(found)


def vermin_command():
    custom = os.environ.get("FLOOR_VERMIN_CMD")
    return shlex.split(custom) if custom else list(DEFAULT_CMD)


def run_vermin(root, files):
    """Run vermin on files (relative to root). -> {rel: [feature, ...]} for each file over the floor."""
    cmd = vermin_command() + FLAGS + files
    try:
        proc = _nowindow.run(cmd, cwd=root, capture_output=True, encoding="utf-8", errors="replace",
                             timeout=TIMEOUT)
    except (OSError, ValueError) as err:
        raise Unreadable("vermin cannot start (%s): %s" % (" ".join(vermin_command()), err))
    except Exception as err:  # subprocess.TimeoutExpired
        raise Unreadable("vermin did not finish: %s" % err)
    findings = {}
    current = None
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        if line[0] not in " \t":
            current = next((rel for rel in files if line.endswith(" " + rel)), None)
            if current is not None:
                findings.setdefault(current, [])
            continue
        text = line.strip()
        if current is None:
            continue
        if text.startswith("error:"):
            raise Unreadable("vermin cannot parse %s: %s" % (current, text))
        findings[current].append(text)
    if proc.returncode == 0 and not findings:
        return {}
    if proc.returncode == 1 and findings:
        return findings
    detail = (proc.stderr.strip().splitlines() or proc.stdout.strip().splitlines() or ["no output"])[-1]
    raise Unreadable("vermin failed (exit %d, is vermin installed?): %s" % (proc.returncode, detail))


def main(argv):
    root = ROOT
    args = list(argv)
    if args:
        if args[0] != "--root" or len(args) != 2:
            print("check_python_floor: usage: check_python_floor.py [--root DIR]")
            return 2
        root = os.path.abspath(args[1])
    try:
        files = product_files(root)
        problems = {}
        for start in range(0, len(files), CHUNK):
            problems.update(run_vermin(root, files[start:start + CHUNK]))
    except Unreadable as err:
        print("check_python_floor: cannot check: %s" % err)
        return 2
    for rel in sorted(problems):
        features = problems[rel] or ["needs more than 3.9"]
        print("%s: needs more than Python 3.9: %s" % (rel, "; ".join(features)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
