"""The one layout: where each kind of file lives in every repo. Every shared tool asks this module.

lint/layout.json holds the kinds. A repo adds its own kinds in its extras file (the layout's
"extras" path, read from the repo root): {"kinds": {"<name>": {"path": "<folder>", ...}}}. An
extra kind may not replace a layout kind. The extras file may hold no kinds: it is also the mark
that the repo has rolled out to the layout.

BANDAID, named: a repo that has not rolled out is read where the shared tools read it before the
layout, through the layout's "legacy" map, so no tool changes its verdict on a repo before then. Cause: each repo moves its own files in its own
roll-out (owner, Oct 17). The last roll-out deletes "legacy", `legacy()`, `candidates()` and the
branch in `path()`.

Standard library only, and safe to import: it reads files only when a function is called.
"""
import json
import os

LAYOUT_FILE = "lint/layout.json"  # relative to the claude-settings root; hooks/guard.py holds the same literal
LAYOUT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.basename(LAYOUT_FILE))


class LayoutError(Exception):
    """The layout file or a repo's extras file cannot be read or has the wrong shape."""


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as err:
        raise LayoutError("cannot read %s: %s" % (path, err)) from err
    if not isinstance(data, dict) or not isinstance(data.get("kinds"), dict):
        raise LayoutError("%s: no \"kinds\" object" % path)
    for name, kind in data["kinds"].items():
        if not isinstance(kind, dict) or not isinstance(kind.get("path"), str) or not kind["path"].strip("/"):
            raise LayoutError("%s: kind %s has no path" % (path, name))
    return data


def layout():
    """The layout file, as read."""
    return _read(LAYOUT_PATH)


def _extras(root):
    return os.path.join(root, *layout().get("extras", "").split("/"))


def rolled_out(root):
    """True when `root` holds its extras file, so it keeps every kind at its layout path."""
    return bool(layout().get("extras")) and os.path.isfile(_extras(root))


def kinds(root=None):
    """{name: kind} from the layout, plus the kinds in the extras file of `root` when it has one."""
    found = {name: dict(kind) for name, kind in layout()["kinds"].items()}
    if root is not None and rolled_out(root):
        for name, kind in _read(_extras(root))["kinds"].items():
            if name in found:
                raise LayoutError("%s: kind %s is in the layout already" % (_extras(root), name))
            found[name] = dict(kind, set="extra")
    return found


def legacy(name):
    """Where the shared tools read kind `name` before the layout, else its layout path."""
    found = layout()["kinds"][name]["path"].strip("/")
    return layout().get("legacy", {}).get(found, found)


def path(root, name):
    """The path of kind `name` in `root`, relative to it, with `/` separators: the layout path in a
    rolled-out repo, else the legacy path."""
    if rolled_out(root):
        return kinds(root)[name]["path"].strip("/")
    return legacy(name)


def candidates(root, name):
    """`path(root, name)`, then the layout path when it differs: for a reader that takes the first
    one that exists, as STE lint's gloss collapse does."""
    first, then = path(root, name), layout()["kinds"][name]["path"].strip("/")
    return (first,) if first == then else (first, then)


def folders(root, flag):
    """The paths in `root` of each kind whose `flag` (record, listed) is true, in layout order."""
    return tuple(path(root, name) for name, kind in kinds(root).items() if kind.get(flag))
