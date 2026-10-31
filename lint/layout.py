"""The one layout: where each kind of file lives in every repo. Every shared tool asks this module.

lint/layout.json holds the kinds. A repo adds its own kinds in its extras file (the layout's
"extras" path, read from the repo root): {"kinds": {"<name>": {"path": "<folder>", ...}}}. An
extra kind may not replace a layout kind. The mark that the repo has rolled out to the layout is
its own key in that file, "rolled-out": true (ROLLED_OUT; decision one-layout-every-repo). An
extras file with no mark does not roll a repo out. Its keys that are not about folder placement
("waiting-page", "waiting-page-colour", "waiting-page-icon", "kind", "caution", "visibility",
"devices", "shared-resources", "roadmap", "record-branch") read whenever the file exists (`has_extras()`). The
"waiting-page" key holds the URL of the repo's waiting page (`waiting_page()`, skill waiting-page);
"waiting-page-colour" (#rrggbb) and "waiting-page-icon" (an .svg or .png path in the repo) are its
branding (`waiting_page_colour()`, `waiting_page_icon()`, read by lint/repo_colour.py). The "record-branch" key
names the branch of the record in a fork worktree (`record_branch()`); with no key it is "roadmap".
`set_waiting_page()` writes the "waiting-page" key once, for triage; it never writes "rolled-out".

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


ROLLED_OUT = "rolled-out"  # the extras key that marks a repo as rolled out to the layout


def has_extras(root):
    """True when `root` holds its extras file. The keys that are not about folder placement read from it."""
    return bool(layout().get("extras")) and os.path.isfile(_extras(root))


def rolled_out(root):
    """True when `root` holds its extras file and the file's "rolled-out" key is true, so it keeps
    every kind at its layout path."""
    return has_extras(root) and _read(_extras(root)).get(ROLLED_OUT) is True


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


def _artifact_link(found, where):
    """`found` when it is a claude.ai artifact link, else LayoutError."""
    if not isinstance(found, str) or not found.startswith(ARTIFACT_LINK):
        raise LayoutError("%s: %s is not a claude.ai artifact link" % (where, WAITING_PAGE))
    return found


def waiting_page(root):
    """The URL of the waiting page of `root` (skill waiting-page), from its extras file, mark or not.
    "unknown" when the repo has no extras file or no key: a repo with no page is not an error."""
    if not has_extras(root):
        return "unknown"
    found = _read(_extras(root)).get(WAITING_PAGE)
    if found is None:
        return "unknown"
    return _artifact_link(found, _extras(root))


def set_waiting_page(root, url):
    """Write the "waiting-page" key of `root`'s extras file, creating the file when missing. True when it
    wrote; False when the key is already set, with the file left byte-identical. LayoutError when `url`
    is not an artifact link. No other key is written, "rolled-out" least of all."""
    _artifact_link(url, _extras(root))
    if has_extras(root):
        data = _read(_extras(root))
        if WAITING_PAGE in data:
            return False
    else:
        data = {"kinds": {}}
    data[WAITING_PAGE] = url
    os.makedirs(os.path.dirname(_extras(root)), exist_ok=True)
    with open(_extras(root), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    return True


RECORD_BRANCH = "record-branch"  # the extras key: the branch that holds this worktree's record
DEFAULT_RECORD_BRANCH = "roadmap"


def record_branch(root):
    """The record branch of `root` from its extras file: the "record-branch" key, else "roadmap". A fork
    worktree sets its own. LayoutError when the key is not a plain git branch name."""
    keys = _repo_keys(root)
    if RECORD_BRANCH not in keys:
        return DEFAULT_RECORD_BRANCH
    found = keys[RECORD_BRANCH]
    if (not isinstance(found, str) or not re.fullmatch(r"[A-Za-z0-9._][A-Za-z0-9._/-]*", found)
            or ".." in found or "//" in found or found.endswith(("/", ".lock"))):
        raise LayoutError("%s: %s %r is not a branch name" % (_extras(root), RECORD_BRANCH, found))
    return found


WAITING_PAGE_COLOUR = "waiting-page-colour"  # the extras key: the page's colour, #rrggbb
WAITING_PAGE_ICON = "waiting-page-icon"  # the extras key: the page's icon file, a path inside the repo


def waiting_page_colour(root):
    """The waiting page colour of `root` from its extras file, lowercased; None when unset. LayoutError
    when it is not #rrggbb, so a caller never guesses one."""
    found = _repo_keys(root).get(WAITING_PAGE_COLOUR)
    if found is None:
        return None
    if not isinstance(found, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", found):
        raise LayoutError("%s: %s %r is not #rrggbb" % (_extras(root), WAITING_PAGE_COLOUR, found))
    return found.lower()


def waiting_page_icon(root):
    """The path, relative to `root`, of its waiting page icon from its extras file; None when unset.
    LayoutError when it is not a path inside the repo. The file itself is the caller's to read."""
    found = _repo_keys(root).get(WAITING_PAGE_ICON)
    if found is None:
        return None
    where = "%s: %s" % (_extras(root), WAITING_PAGE_ICON)
    if not isinstance(found, str) or not found.strip("/ ") or found != found.strip():
        raise LayoutError("%s %r is not a path" % (where, found))
    return _safe(found, where)


def live_pages(roots):
    """[(owner, url)] for every root in `roots` that has a waiting page, in order: the one list of
    live waiting pages (skill waiting-page). The owner is the repo's folder name. A root with no
    page is left out, because it has none; a bad link is a LayoutError."""
    found = []
    for root in roots:
        url = waiting_page(os.path.abspath(root))
        if url != "unknown":
            found.append((os.path.basename(os.path.abspath(root)), url))
    return found


def _repo_keys(root):
    """The extras file of `root` as a dict, or {} when the repo has none."""
    return _read(_extras(root)) if has_extras(root) else {}


def _named(root, key, table):
    """The value of extras key `key` when it names an entry of layout table `table`, None when unset.
    LayoutError when it names no entry."""
    found = _repo_keys(root).get(key)
    if found is None:
        return None
    if not isinstance(found, str) or found not in layout().get(table, {}):
        raise LayoutError("%s: %s %r is not one of %s" % (_extras(root), key, found, ", ".join(layout().get(table, {}))))
    return found


def devices(root):
    """[{id, name, size}] for the repo at `root`, first device first: the repo's own "devices" list, else
    the default order of its "kind". None (printed as `unknown`) when the repo names neither. A size is
    None until a written source gives it (lint/layout.json, "devices"): no size is ever guessed."""
    keys, table = _repo_keys(root), layout().get("devices", {})
    listed = keys.get("devices")
    kind = _named(root, "kind", "app-kinds")
    if listed is None:
        if kind is None:
            return None
        listed = layout()["app-kinds"][kind]["devices"]
    if not isinstance(listed, list) or not listed or any(item not in table for item in listed):
        raise LayoutError("%s: devices is not a list of %s" % (_extras(root), ", ".join(table)))
    return [dict(table[item], id=item) for item in listed]


def caution(root):
    """{level, facts, acts} for the repo at `root`: its "caution" key, else the level its "visibility"
    key maps to, else the layout's default (public). The visibility source is a key in the extras file,
    so it reads offline."""
    level = _named(root, "caution", "cautions")
    if level is None:
        by, seen = layout().get("visibility-caution", {}), _repo_keys(root).get("visibility")
        level = by.get(seen, by["default"]) if isinstance(seen, str) and seen != "default" else by["default"]
        if level not in layout().get("cautions", {}):
            raise LayoutError("%s: visibility-caution maps to no caution level" % LAYOUT_FILE)
    found = layout()["cautions"][level]
    return {"level": level, "facts": list(found["facts"]), "acts": list(found["acts"])}


def describe_devices(root):
    """The text `layout.py devices` prints: one device per line, the first one drawn first."""
    found = devices(root)
    if found is None:
        return "unknown"
    return "\n".join("%s: %s; size %s" % (d["id"], d["name"], _size(d.get("size"))) for d in found)


def _size(size):
    if size is None:
        return "not written"
    return "%s (%s)" % (size.get("text", ""), size["source"])


def describe_caution(root):
    """The text `layout.py caution` prints, and session start prints: the level, its facts, its acts."""
    found = caution(root)
    return "\n".join(["caution: " + found["level"]] + ["fact: " + f for f in found["facts"]]
                      + ["act: " + a for a in found["acts"]])


SHARED_RESOURCES = "shared-resources"  # the extras key: [{name, owner, preflight, holds}]


def shared_resources(root):
    """[{name, owner, preflight, holds}] from the "shared-resources" key of `root`'s extras file, [] when
    it has none. owner is `<gh-owner>/<repo>`; preflight and holds are paths inside the owner repo. When
    `root` is the owner, its preflight file must exist. LayoutError names the extras file and the entry."""
    found = _repo_keys(root).get(SHARED_RESOURCES)
    if found is None:
        return []
    where = _extras(root)
    if not isinstance(found, list):
        raise LayoutError("%s: %s is not a list" % (where, SHARED_RESOURCES))
    names = set()
    for number, item in enumerate(found, 1):
        label = "%s entry %d (%s)" % (SHARED_RESOURCES, number, item.get("name") if isinstance(item, dict) else item)
        if not isinstance(item, dict):
            raise LayoutError("%s: %s is not an object" % (where, label))
        for field in ("name", "owner", "preflight") + (("holds",) if "holds" in item else ()):
            if not isinstance(item.get(field), str) or not item[field].strip("/ "):
                raise LayoutError("%s: %s has no %s" % (where, label, field))
        if item["name"] in names:
            raise LayoutError("%s: %s name appears twice" % (where, label))
        names.add(item["name"])
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", item["owner"]) or item["owner"].endswith(".git"):
            raise LayoutError("%s: %s owner %r is not <owner>/<repo>" % (where, label, item["owner"]))
        for field in ("preflight", "holds"):
            if field in item:
                if item[field] != item[field].strip():
                    raise LayoutError("%s: %s %s has whitespace around it" % (where, label, field))
                _safe(item[field], "%s: %s %s" % (where, label, field))
        if repo_name(root) == item["owner"].lower() and not os.path.isfile(os.path.join(root, *item["preflight"].split("/"))):
            raise LayoutError("%s: %s preflight %s is missing in the owner repo" % (where, label, item["preflight"]))
    return found


def folders(root, flag):
    """The paths in `root` of each kind whose `flag` (record, listed) is true, in layout order."""
    return tuple(path(root, name) for name, kind in kinds(root).items() if kind.get(flag))


if __name__ == "__main__":
    import sys
    # python3 lint/layout.py path <root> <kind>: one path, for a shell step.
    # python3 lint/layout.py waiting-page <root>: the page URL, or "unknown".
    # Pages of several repos: live_pages(roots), read by skills/waiting-page/stale_pages.py.
    # python3 lint/layout.py devices <root>: the repo's devices, first drawn first, or "unknown".
    # python3 lint/layout.py caution <root>: the repo's caution level with its facts and acts.
    # python3 lint/layout.py shared-resources <root>: the repo's shared machines as JSON, [] when none.
    # python3 lint/layout.py set-waiting-page <url>: write the key once into the current folder's extras
    # file. Exit 0 wrote it; 1 already set (prints the URL); 2 bad URL or unreadable file.
    ROOT_VERBS = (WAITING_PAGE, "devices", "caution", SHARED_RESOURCES)
    if len(sys.argv) == 3 and sys.argv[1] == "set-waiting-page":
        try:
            here = os.getcwd()
            if set_waiting_page(here, sys.argv[2]):
                sys.exit(0)
            print(waiting_page(here))
            sys.exit(1)
        except LayoutError as err:
            print("layout: %s" % err, file=sys.stderr)
            sys.exit(2)
    if not (len(sys.argv) == 4 and sys.argv[1] == "path" or len(sys.argv) == 3 and sys.argv[1] in ROOT_VERBS):
        sys.exit("usage: layout.py path <root> <kind> | layout.py waiting-page|devices|caution|shared-resources <root> | layout.py set-waiting-page <url>")
    try:
        here = os.path.abspath(sys.argv[2])
        if sys.argv[1] == WAITING_PAGE:
            print(waiting_page(here))
        elif sys.argv[1] == "devices":
            print(describe_devices(here))
        elif sys.argv[1] == "caution":
            print(describe_caution(here))
        elif sys.argv[1] == SHARED_RESOURCES:
            print(json.dumps(shared_resources(here)))
        else:
            print(path(here, sys.argv[3]))
    except (LayoutError, KeyError) as err:
        sys.exit("layout: %s" % err)
