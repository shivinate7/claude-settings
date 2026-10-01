#!/usr/bin/env python3
"""Generates the daily Windows Task Scheduler task that sweeps every repository.

Writes an XML task definition file. NOBODY COMMITS THAT FILE: it names an absolute path on one
machine, and this repository never holds a tracked absolute path. `install_launchd.py`'s module
docstring gives the same reasoning for the `.plist` it writes.

REFUSES TO RUN FROM A LINKED WORKTREE. A task definition GENERATED from a linked worktree would
point its command at a worktree. A worktree is removable, by this very sweep, among other
things. The day it is removed, Task Scheduler is left retrying a directory that no longer
exists, silently, with no session there to notice. So this installer reads its own checkout's
worktree-ness with `hooks/guard.py`'s own tested primitive. That is `is_worktree`, the same
read `janitor/sweep.py`'s discovery and `janitor/install_launchd.py` both use. It refuses
outright, rather than generate a task that would work today and rot on its own. An UNREADABLE
worktree-ness answer refuses too, the same conservative direction `install_launchd.py` takes.
Installing wrong is exactly the kind of mistake that direction exists to avoid. Asking to
"install from the main checkout" again costs nothing.

The TASK NAME is a fixed, generic string. It never names a worktree, a branch, or any path.
Task Scheduler identifies the task by this name alone. A name built from a path would make the
same mistake the refusal above exists to prevent.

This installer only WRITES the XML task definition and PRINTS the `schtasks` command the owner
would run to register it. It never calls `schtasks` itself. Registering a machine-wide daily job
is a separate, later act, on the owner's own word. Never calling it is what keeps this installer
testable on Linux, the same reasoning `install_launchd.py` never calls `launchctl`.

Usage:
    python3 janitor/install_schtasks.py                 # write <output-dir>/<TaskName>.xml
    python3 janitor/install_schtasks.py --hour 3 --minute 17

THE GENERATED COMMAND CARRIES NO `--discover` ROOT. `janitor/sweep.py`, called with no ROOT and
no `--discover`, already resolves its own roots at run time: `janitor.roots` from settings.json,
falling back to `default_discover_roots()`. An installer-side root would be a second, stale copy
of that same list (this file once hard-coded `~/Developer`, a path that does not exist on every
machine and is not where this repository's own clones live). Reading roots at run time means
the registered task never needs re-registering when `janitor.roots` changes.

Testing overrides (never used by a real install): --repo-root, --output-dir.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

TASK_NAME = "claude-settings-janitor-daily-sweep"
TASK_XML_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def resolve_primary_checkout(where: str):
    """Same read `install_launchd.py.resolve_primary_checkout` makes, kept as its own local copy
    here rather than imported across scripts. It reads the parent of the one `.git` directory
    every worktree of a clone shares. Used only to NAME the remedy when refusing."""
    top = guard._git(where, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    toplevel = top.stdout.strip()
    if not toplevel:
        return None
    common = guard._git(toplevel, "rev-parse", "--git-common-dir")
    if common is None or common.returncode != 0:
        return None
    common_dir = common.stdout.strip()
    if not common_dir:
        return None
    try:
        return os.path.dirname(os.path.realpath(os.path.join(toplevel, common_dir)))
    except Exception:
        return None


def build_task_xml(repo_root: str, hour: int, minute: int) -> bytes:
    """Return a minimal, valid Task Scheduler XML task definition as bytes.

    The command is `python <repo>/janitor/sweep.py --confirm`, split into Task Scheduler's own
    `<Command>` (the interpreter) and `<Arguments>` (everything else) fields. No `--discover`
    root: `sweep.py` resolves its own roots at run time (see the module docstring above).
    """
    sweep_py = os.path.join(repo_root, "janitor", "sweep.py")
    arguments = "%s --confirm" % _quote_arg(sweep_py)
    ET.register_namespace("", TASK_XML_NAMESPACE)
    task = ET.Element("{%s}Task" % TASK_XML_NAMESPACE, attrib={"version": "1.2"})

    registration_info = ET.SubElement(task, "{%s}RegistrationInfo" % TASK_XML_NAMESPACE)
    ET.SubElement(registration_info, "{%s}Description" % TASK_XML_NAMESPACE).text = (
        "Daily janitor sweep for repositories under claude-settings."
    )

    triggers = ET.SubElement(task, "{%s}Triggers" % TASK_XML_NAMESPACE)
    calendar_trigger = ET.SubElement(triggers, "{%s}CalendarTrigger" % TASK_XML_NAMESPACE)
    ET.SubElement(calendar_trigger, "{%s}StartBoundary" % TASK_XML_NAMESPACE).text = (
        "2024-01-01T%02d:%02d:00" % (hour, minute)
    )
    ET.SubElement(calendar_trigger, "{%s}Enabled" % TASK_XML_NAMESPACE).text = "true"
    schedule_by_day = ET.SubElement(calendar_trigger, "{%s}ScheduleByDay" % TASK_XML_NAMESPACE)
    ET.SubElement(schedule_by_day, "{%s}DaysInterval" % TASK_XML_NAMESPACE).text = "1"

    settings = ET.SubElement(task, "{%s}Settings" % TASK_XML_NAMESPACE)
    ET.SubElement(settings, "{%s}Enabled" % TASK_XML_NAMESPACE).text = "true"
    ET.SubElement(settings, "{%s}StartWhenAvailable" % TASK_XML_NAMESPACE).text = "true"

    actions = ET.SubElement(task, "{%s}Actions" % TASK_XML_NAMESPACE)
    exec_action = ET.SubElement(actions, "{%s}Exec" % TASK_XML_NAMESPACE)
    ET.SubElement(exec_action, "{%s}Command" % TASK_XML_NAMESPACE).text = sys.executable
    ET.SubElement(exec_action, "{%s}Arguments" % TASK_XML_NAMESPACE).text = arguments

    # `schtasks /create /xml` requires UTF-16. Measured here, same document, unchanged structure:
    #   UTF-8, no BOM      -> "malformed" at (1,40), cannot switch encoding. Exit code 1.
    #   UTF-8, with BOM    -> "malformed" at (1,2), incorrect document syntax. Exit code 1.
    #   UTF-16 LE, with BOM -> the task is created, then deletes cleanly. Exit code 0.
    # This is a requirement of the real tool, not a style choice.
    return ET.tostring(task, encoding="UTF-16", xml_declaration=True)


def _quote_arg(value: str) -> str:
    """Wrap VALUE in double quotes for the `<Arguments>` command line, escaping any quote it
    already holds. A path with a space is the ordinary case this guards against on Windows."""
    return '"%s"' % value.replace('"', '\\"')


def default_output_dir() -> str:
    return os.path.join(guard.config_dir(), "janitor")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hour", type=int, default=3, help="local hour, 0-23 (default 3)")
    parser.add_argument("--minute", type=int, default=17, help="local minute, 0-59 (default 17)")
    parser.add_argument("--repo-root", default=None,
                         help="testing only: the checkout to treat as this installer's own")
    parser.add_argument("--output-dir", default=None,
                         help="testing only: overrides where the task XML is written")
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root) if args.repo_root else REPO_ROOT
    output_dir = os.path.abspath(args.output_dir) if args.output_dir else default_output_dir()

    worktree = guard.is_worktree(repo_root)
    if worktree is not False:
        primary = resolve_primary_checkout(repo_root)
        if worktree is True:
            head = "janitor: refusing to install from a linked worktree (%s)." % repo_root
        else:
            head = ("janitor: could not tell whether %s is a linked worktree; refusing rather "
                     "than guess." % repo_root)
        remedy = ("Install from the main checkout instead%s." %
                  ((": " + primary) if primary else " (its main checkout)"))
        print(head + " " + remedy, file=sys.stderr)
        return 1

    os.makedirs(output_dir, exist_ok=True)

    xml_bytes = build_task_xml(repo_root, args.hour, args.minute)
    xml_path = os.path.join(output_dir, TASK_NAME + ".xml")
    with open(xml_path, "wb") as handle:
        handle.write(xml_bytes)

    print("Wrote %s" % xml_path)
    print('Register it with: schtasks /create /tn "%s" /xml "%s" /f' % (TASK_NAME, xml_path))
    print('Unregister it with: schtasks /delete /tn "%s" /f' % TASK_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
