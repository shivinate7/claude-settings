"""The one layout: where each kind of file lives in every repo. Every shared tool asks this module.

lint/layout.json holds the kinds. A repo adds its own kinds in its extras file (the layout's
"extras" path, read from the repo root): {"kinds": {"<name>": {"path": "<folder>", ...}}}. An
extra kind may not replace a layout kind. The extras file may hold no kinds: it is also the mark
that the repo has rolled out to the layout. Its "waiting-page" key holds the URL of the repo's
waiting page (`waiting_page()`, skill waiting-page).

BANDAID, named: a repo that has not rolled out is read where the shared tools read it before the
layout, through the layout's "legacy" map, so no tool changes its verdict on a repo before then. A kind
that one repo holds somewhere of its own (q_max's specs/todo.md) sits in "legacy-repos" under the
repo's GitHub name, rolled out or not, and that repo's extras file may repeat it but not move it.
Cause: each repo moves its own files in its own roll-out (owner, Oct 17). The last roll-out deletes
"legacy", "legacy-repos", `legacy()`, `legacy_repos()`, `unmoved()`, `candidates()` and the branches in `path()`.

Standard library only, and safe to import: it reads files only when a function is called.
"""
import json
import os
import re

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
            if name in found and kind["path"].strip("/") in _kept(name):
                continue  # the extras file repeats a place legacy-repos keeps this kind
            if name in found:
                raise LayoutError("%s: kind %s is in the layout already" % (_extras(root), name))
            _safe(kind["path"], _extras(root))
            found[name] = dict(kind, set="extra")
    return found


def legacy(name):
    """Where the shared tools read kind `name` before the layout, else its layout path."""
    found = layout()["kinds"][name]["path"].strip("/")
    return layout().get("legacy", {}).get(found, found)


# github.com in https, ssh and scp form, and the /git/<owner>/<name> path of a cloud session's git proxy.
GITHUB = re.compile(r"(?:^|[/@])github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/*$|/git/([^/\s]+/[^/\s]+?)(?:\.git)?/*$")


def _common_dir(root):
    """The git folder that holds the config of the checkout at `root`, a linked worktree too, or None."""
    found = os.path.join(root, ".git")
    if os.path.isfile(found):
        with open(found, encoding="utf-8", errors="replace") as handle:
            line = handle.read().strip()
        if not line.startswith("gitdir:"):
            return None
        found = os.path.join(root, line[len("gitdir:"):].strip())
        try:
            with open(os.path.join(found, "commondir"), encoding="utf-8", errors="replace") as handle:
                found = os.path.join(found, handle.read().strip())
        except OSError:
            pass  # a git dir with no commondir file is its own common dir
    return found if os.path.isdir(found) else None


def repo_name(root):
    """`owner/name` of the GitHub origin of the checkout at `root`, lowercased, from git's config file
    with no process started. None when it has no git folder, no origin or an origin off GitHub."""
    try:
        folder = _common_dir(root)
        if folder is None:
            return None
        with open(os.path.join(folder, "config"), encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except (OSError, ValueError):  # ValueError: a path with a NUL byte
        return None
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == '[remote "origin"]' and re.match(r"url\s*=", line):
            hit = GITHUB.search(line.split("=", 1)[1].strip())
            return (hit.group(1) or hit.group(2)).lower() if hit else None
    return None


def legacy_repos():
    """{owner/name: {kind: path}} from the layout's "legacy-repos", keys lowercased. LayoutError when an
    entry names a kind the layout has not, or a path outside the repo."""
    found, names = layout().get("legacy-repos", {}), layout()["kinds"]
    if not isinstance(found, dict) or not all(isinstance(entry, dict) for entry in found.values()):
        raise LayoutError("%s: legacy-repos is not {repo: {kind: path}}" % LAYOUT_FILE)
    for repo, entry in found.items():
        for name, where in entry.items():
            if name not in names:
                raise LayoutError("%s: legacy-repos %s names kind %s, which the layout has not" % (LAYOUT_FILE, repo, name))
            if not isinstance(where, str) or not where.strip("/"):
                raise LayoutError("%s: legacy-repos %s kind %s has no path" % (LAYOUT_FILE, repo, name))
            _safe(where, "%s: legacy-repos %s" % (LAYOUT_FILE, repo))
    return {repo.lower(): entry for repo, entry in found.items()}


def _kept(name):
    """Every path legacy-repos keeps kind `name` at, in any repo."""
    return {entry[name].strip("/") for entry in legacy_repos().values() if name in entry}


def unmoved(root):
    """{kind: path} for each kind the repo at `root` still holds where legacy-repos says: by its
    origin's name, else by its extras file repeating one of those paths (an origin may be unreadable)."""
    name = repo_name(root)
    found = {kind: where.strip("/") for kind, where in (legacy_repos().get(name, {}) if name else {}).items()}
    if rolled_out(root):
        for kind, entry in _read(_extras(root))["kinds"].items():
            if kind not in found and isinstance(entry, dict) and entry["path"].strip("/") in _kept(kind):
                found[kind] = entry["path"].strip("/")
    return found


def path(root, name):
    """The path of kind `name` in `root`, relative to it, with `/` separators: the repo's legacy-repos
    path when it has one, else the layout path in a rolled-out repo, else the legacy path."""
    kept = unmoved(root).get(name)
    if kept:
        return kept
    if rolled_out(root):
        return kinds(root)[name]["path"].strip("/")
    return legacy(name)


def candidates(root, name):
    """`path(root, name)`, then the layout path when it differs: for a reader that takes the first
    one that exists, as STE lint's gloss collapse does."""
    first, then = path(root, name), layout()["kinds"][name]["path"].strip("/")
    return (first,) if first == then else (first, then)


def _safe(found, where):
    """`found` when it is a relative path inside the repo, else LayoutError."""
    parts = found.replace("\\", "/").split("/")
    if os.path.isabs(found) or found.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
        raise LayoutError("%s: path %r is not inside the repo" % (where, found))
    return found


WAITING_PAGE = "waiting-page"  # the extras key that holds the repo's waiting page URL
ARTIFACT_LINK = ("https://claude.ai/artifact/", "https://claude.ai/code/artifact/")


def waiting_page(root):
    """The URL of the waiting page of `root` (skill waiting-page), from its extras file. "unknown"
    when the repo has no extras file or no key: a repo with no page is not an error."""
    if not rolled_out(root):
        return "unknown"
    found = _read(_extras(root)).get(WAITING_PAGE)
    if found is None:
        return "unknown"
    if not isinstance(found, str) or not found.startswith(ARTIFACT_LINK):
        raise LayoutError("%s: %s is not a claude.ai artifact link" % (_extras(root), WAITING_PAGE))
    return found


def folders(root, flag):
    """The paths in `root` of each kind whose `flag` (record, listed) is true, in layout order."""
    return tuple(path(root, name) for name, kind in kinds(root).items() if kind.get(flag))


if __name__ == "__main__":
    import sys
    # python3 lint/layout.py path <root> <kind>: one path, for a shell step.
    # python3 lint/layout.py waiting-page <root>: the page URL, or "unknown".
    if not (len(sys.argv) == 4 and sys.argv[1] == "path" or len(sys.argv) == 3 and sys.argv[1] == WAITING_PAGE):
        sys.exit("usage: layout.py path <root> <kind> | layout.py waiting-page <root>")
    try:
        if sys.argv[1] == WAITING_PAGE:
            print(waiting_page(os.path.abspath(sys.argv[2])))
        else:
            print(path(os.path.abspath(sys.argv[2]), sys.argv[3]))
    except (LayoutError, KeyError) as err:
        sys.exit("layout: %s" % err)
