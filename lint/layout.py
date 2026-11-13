"""The one layout: where each kind of file lives in every repo. Every shared tool asks this module.

lint/layout.json holds the kinds. A repo adds its own kinds in its extras file (the layout's
"extras" path, read from the repo root): {"kinds": {"<name>": {"path": "<folder>", ...}}}. An
extra kind may not replace a layout kind. The mark that the repo has rolled out to the layout is
its own key in that file, "rolled-out": true (ROLLED_OUT; decision one-layout-every-repo). An
extras file with no mark does not roll a repo out. Its keys that are not about folder placement
("waiting-page", "waiting-page-colour", "waiting-page-icon", "page-writer", "kind", "caution", "visibility",
"devices", "shared-resources", "roadmap", "record-branch", "artifacts") read whenever the file exists (`has_extras()`). The
"artifacts" key is the registry of the claude.ai artifacts the repo holds (`artifacts()`, decision waiting-data-in-repo).
The "waiting-page" key holds the URL of the repo's waiting page (`waiting_page()`, skill waiting-page), the fallback after
the registry entry whose role is "waiting-page";
"waiting-page-colour" (#rrggbb) and "waiting-page-icon" (an .svg or .png path in the repo) are its
branding (`waiting_page_colour()`, `waiting_page_icon()`, read by lint/repo_colour.py). "page-writer" is the session id
of the page's writer (`page_writer_key()`, read by the pick guard in lint/report_guard.py). The "record-branch" key
names the branch of the record in a fork worktree (`record_branch()`); with no key it is "roadmap".
`set_waiting_page()` writes the "waiting-page" key once, for triage; it never writes "rolled-out".

BANDAID, named: a repo that has not rolled out is read where the shared tools read it before the
layout, through the layout's "legacy" map, so no tool changes its verdict on a repo before then. A kind
that one repo holds somewhere of its own (q_max's specs/todo.md) sits in "legacy-repos" under the
repo's GitHub name, rolled out or not, and that repo's extras file may repeat it but not move it.
Cause: each repo moves its own files in its own roll-out (owner, Oct 17). The last roll-out deletes
"legacy", "legacy-repos", `legacy()`, `legacy_repos()`, `unmoved()`, `candidates()` and the branches in `path()`.

Safe to import: it reads files only when a function is called. It needs the standard library and
hooks/git_reads.py, which `repo_name` imports on first use.
"""
import json
import ntpath
import os
import posixpath
import re
import subprocess
import sys

LAYOUT_FILE = "lint/layout.json"  # relative to the claude-settings root; hooks/guard.py holds the same literal
LAYOUT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.basename(LAYOUT_FILE))


class LayoutError(Exception):
    """The layout file or a repo's extras file cannot be read or has the wrong shape."""


class BranchNameError(LayoutError):
    """The extras file reads, and its "record-branch" key is not a branch name."""


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return _parse(handle.read(), path)
    except OSError as err:
        raise LayoutError("cannot read %s: %s" % (path, err)) from err


def _parse(text, path):
    """The extras or layout text as a dict. `path` names the source in an error."""
    try:
        data = json.loads(text)
    except ValueError as err:
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
                extras, held = _extras(root), found[name]["path"].strip("/")
                if kind["path"].strip("/") == held:
                    raise LayoutError("%s: the layout holds kind %s at %s now; delete it from %s" % (extras, name, held, extras))
                raise LayoutError("%s: kind %s is in the layout at %s; this file puts it at %s" % (extras, name, held, kind["path"].strip("/")))
            _safe(kind["path"], _extras(root))
            found[name] = dict(kind, set="extra")
    return found


def legacy(name):
    """Where the shared tools read kind `name` before the layout, else its layout path."""
    found = layout()["kinds"][name]["path"].strip("/")
    return layout().get("legacy", {}).get(found, found)


# An origin repo_name may read: github.com in https, ssh and scp form, a port after the host allowed, or the
# /git/<owner>/<name> path of a cloud session's git proxy. The path is exactly owner/name, `.git` and trailing
# slashes optional; git_reads.origin_slug reads the owner/name.
GITHUB = re.compile(
    r"(?:^|[/@])github\.com(?::\d+)?[:/]+[^/\s]+/[^/\s]+?(?:\.git)?/*$|/git/[^/\s]+/[^/\s]+?(?:\.git)?/*$")


def _origin_slug(url):
    """git_reads.origin_slug, the one origin parser; imported on first use so this module stays safe to import."""
    hooks = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "hooks")
    if hooks not in sys.path:
        sys.path.append(hooks)
    from git_reads import origin_slug
    return origin_slug(url)


def _nowindow_run(*args, **kwargs):
    """hooks/_nowindow.run, the one route that starts a process with no console window; imported on first use."""
    hooks = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "hooks")
    if hooks not in sys.path:
        sys.path.append(hooks)
    from _nowindow import run
    return run(*args, **kwargs)


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
            url = line.split("=", 1)[1].strip()
            slug = _origin_slug(url) if GITHUB.search(url) else None
            return slug.lower() if slug else None
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
# What a write accepts. A read keeps the looser ARTIFACT_LINK prefix: other repos hold keys written before this.
ARTIFACT_URL = re.compile(r"https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+")


def _artifact_link(found, where):
    """`found` when it is a claude.ai artifact link, else LayoutError."""
    if not isinstance(found, str) or not found.startswith(ARTIFACT_LINK):
        raise LayoutError("%s: %s is not a claude.ai artifact link" % (where, WAITING_PAGE))
    return found


def artifact_id(url):
    """The artifact id of a claude.ai artifact link: its last path segment, with a trailing slash, a query
    and a fragment ignored. "" when `url` is no string or names no id, as a bare `.../artifact/` does. The one
    home of "same artifact", so the /artifact/ and /code/artifact/ forms of one page compare equal."""
    if not isinstance(url, str):
        return ""
    found = url.split("#", 1)[0].split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    return "" if found == "artifact" else found


def is_waiting_page_url(root, url):
    """True when `url` names the waiting page of `root` (same artifact id), false for a repo with no page."""
    page = waiting_page(root)
    return page != "unknown" and bool(artifact_id(page)) and artifact_id(page) == artifact_id(url)


ARTIFACTS = "artifacts"  # the extras key: the registry, a list of {id, url, role, account, collections, export}
WAITING_ROLE = "waiting-page"  # the role of the registry entry that is the repo's waiting page
ARTIFACT_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")  # a slug of 32 characters or fewer, as a record slug is (git-slug-then-claim-number)
ROLE = re.compile(r"[a-z0-9][a-z0-9-]*")
COLLECTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
WAITING_COLLECTIONS = ("items", "answers", "groups", "asks", "meta")  # what the waiting page's database holds


def artifacts(root):
    """[{id, url, role, account, collections, export}] from the "artifacts" key of `root`'s extras file, in order; []
    for a repo with no extras file or no key. `collections` and `export` are filled in: the waiting-page role exports
    the five waiting collections to the waiting-data folder of the record branch, any other role needs its own
    `collections` and exports to `artifacts/<id>/`. A page-only entry (any other role, `"collections": []`) exports its page
    and files and no database; an empty list is refused on the waiting-page role, and a missing key on any other. An entry with `"export": false` (never the waiting-page role) is held and never exported: it needs
    no collections and reads with `export` False and `collections` []. LayoutError, naming the entry by its id, for an email as account, a
    repeated id, an id over 32 characters, a url that is no artifact link, a second waiting-page role or an unsafe path."""
    return _registry(root, _repo_keys(root).get(ARTIFACTS), _extras(root))


def _registry(root, found, where):
    """artifacts(root) for the "artifacts" value `found`, read from `where` (a path, or a ref and path in an error)."""
    if found is None:
        return []
    if not isinstance(found, list):
        raise LayoutError("%s: %s is not a list" % (where, ARTIFACTS))
    seen, out = set(), []
    for number, item in enumerate(found, 1):
        label = "%s entry %d (%s)" % (ARTIFACTS, number, item.get("id") if isinstance(item, dict) else item)
        if not isinstance(item, dict):
            raise LayoutError("%s: %s is not an object" % (where, label))
        entry_id = item.get("id")
        if not isinstance(entry_id, str) or not ARTIFACT_ID.fullmatch(entry_id):
            raise LayoutError("%s: %s id is not 1 to 32 characters of A-Z a-z 0-9 _ -" % (where, label))
        if entry_id in seen:
            raise LayoutError("%s: %s id %s appears twice" % (where, label, entry_id))
        seen.add(entry_id)
        if not isinstance(item.get("url"), str) or not item["url"].startswith(ARTIFACT_LINK) or not artifact_id(item["url"]):
            raise LayoutError("%s: %s (id %s) url is not a claude.ai artifact link with an id" % (where, label, entry_id))
        role = item.get("role")
        if not isinstance(role, str) or not ROLE.fullmatch(role):
            raise LayoutError("%s: %s (id %s) role is not a lowercase slug" % (where, label, entry_id))
        account = item.get("account")
        if not isinstance(account, str) or not account.strip() or account != account.strip() or "@" in account:
            raise LayoutError("%s: %s (id %s) account is not a plain label, and never an email" % (where, label, entry_id))
        no_export = item.get("export") is False  # the repo holds the page and never exports it: no collections, no path
        if no_export and role == WAITING_ROLE:  # the waiting page is the one entry a session must always export
            raise LayoutError("%s: %s (id %s) is the waiting page and cannot be held with export false" % (where, label, entry_id))
        if "collections" in item:
            names = item["collections"]
            if not isinstance(names, list) or (not names and role == WAITING_ROLE) or len(set(names)) != len(names) \
                    or not all(isinstance(n, str) and COLLECTION.fullmatch(n) for n in names):
                raise LayoutError("%s: %s (id %s) collections is not a list of distinct collection names" % (where, label, entry_id))
        elif no_export:
            names = []
        elif role == WAITING_ROLE:
            names = list(WAITING_COLLECTIONS)
        else:
            raise LayoutError("%s: %s (id %s) has no collections to export" % (where, label, entry_id))
        if no_export:
            target = False
        elif "export" in item:
            target = item["export"]
            if not isinstance(target, str) or not target.strip("/") or target != target.strip():
                raise LayoutError("%s: %s (id %s) export is not a path" % (where, label, entry_id))
            target = _safe(target, "%s: %s (id %s) export" % (where, label, entry_id)).strip("/")
        else:
            target = path(root, "waiting-data") if role == WAITING_ROLE else "artifacts/" + entry_id
        out.append(dict(item, collections=list(names), export=target))
    if sum(1 for e in out if e["role"] == WAITING_ROLE) > 1:
        raise LayoutError("%s: %s holds more than one entry with the role %s" % (where, ARTIFACTS, WAITING_ROLE))
    return out


GIT_SHOW_TIMEOUT = 10  # seconds one `git show` may run


def _default_branch_extras(root):
    """The extras file of `root` as read from the repo's default branch, (dict, "<ref>:<path>"), else None. For a
    checkout that holds no extras file of its own, such as a worktree on the record branch. It reads origin/HEAD's
    branch, else origin/main, from the ref alone: no checkout moves and no fetch runs. None for no extras path, no
    such ref, a git error or a timeout, and for a file that does not parse.
    Cost: at most two `git show` processes per call (the second only when origin/HEAD does not resolve), and
    only when the checkout holds no extras file. No file is written."""
    where = layout().get("extras")
    if not where:
        return None
    for ref in ("origin/HEAD", "origin/main"):
        try:
            done = _nowindow_run(["git", "-C", root, "show", "%s:%s" % (ref, where)], capture_output=True,
                                 stdin=subprocess.DEVNULL, timeout=GIT_SHOW_TIMEOUT)
            if done.returncode == 0:
                return _parse(done.stdout.decode("utf-8"), "%s:%s" % (ref, where)), "%s:%s" % (ref, where)
        except (OSError, ValueError, subprocess.SubprocessError, LayoutError, ImportError):
            continue
    return None


def _page_in(root, keys, where):
    """The waiting page URL held by the extras dict `keys` (read from `where`), else "unknown"."""
    for entry in _registry(root, keys.get(ARTIFACTS), where):
        if entry["role"] == WAITING_ROLE:
            return entry["url"]
    found = keys.get(WAITING_PAGE)
    return "unknown" if found is None else _artifact_link(found, where)


def waiting_page(root):
    """The URL of the waiting page of `root` (skill waiting-page): the url of the registry entry whose role is
    "waiting-page", else the old "waiting-page" key, from its extras file, mark or not. A checkout with no extras
    file reads it from the default branch's (_default_branch_extras); its own file always wins.
    "unknown" when the repo has no extras file and no page: a repo with no page is not an error."""
    if has_extras(root):
        return _page_in(root, _read(_extras(root)), _extras(root))
    held = _default_branch_extras(root)
    if held is None:
        return "unknown"
    try:
        return _page_in(root, *held)
    except LayoutError:
        return "unknown"  # a ref's file that does not hold a page is no page, never an error


def set_waiting_page(root, url):
    """Write the waiting page URL into `root`'s extras file, creating the file when missing. A registry entry with the
    role "waiting-page" gets its url updated: True when that changed it, False when it names the same artifact. With no
    such entry, the old "waiting-page" key is written once: True when it wrote; False when the key is already set (a
    null value is unset), with the file left byte-identical. LayoutError when `url` is not an artifact link with an
    id. No other key is written, "rolled-out" least of all."""
    _artifact_link(url, _extras(root))
    if not ARTIFACT_URL.fullmatch(url):
        raise LayoutError("%s: %s %r is not a claude.ai artifact link with an id" % (_extras(root), WAITING_PAGE, url))
    if has_extras(root):
        data = _read(_extras(root))
        held = next((e for e in artifacts(root) if e["role"] == WAITING_ROLE), None)
        if held is not None:
            if artifact_id(held["url"]) == artifact_id(url):
                return False
            data[ARTIFACTS][[e["id"] for e in artifacts(root)].index(held["id"])]["url"] = url
        elif data.get(WAITING_PAGE) is not None:
            return False
        else:
            data[WAITING_PAGE] = url
    else:
        data = {"kinds": {}, WAITING_PAGE: url}
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
        raise BranchNameError("%s: %s %r is not a branch name" % (_extras(root), RECORD_BRANCH, found))
    return found


WAITING_PAGE_COLOUR = "waiting-page-colour"  # the extras key: the page's colour, #rrggbb
WAITING_PAGE_ICON = "waiting-page-icon"  # the extras key: the page's icon file, a path inside the repo
PAGE_WRITER_KEY = "page-writer"  # the extras key: the session id of the page's writer
PARENT_TARGETS = frozenset({"@parent", "parent"})  # send targets that name the parent, never a session id


def page_writer_key(root):
    """The session id of the waiting page's writer from the extras file of `root`; None when the key is missing,
    null, not a string, blank, padded with whitespace or a parent alias (PARENT_TARGETS). A session id is a
    claim, not checked past that."""
    found = _repo_keys(root).get(PAGE_WRITER_KEY)
    if not isinstance(found, str) or not found or found != found.strip() or found in PARENT_TARGETS:
        return None
    return found


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
    key maps to. A missing, non-string, "default" or unmapped visibility resolves to the layout's default,
    "unknown", never to "public". The visibility source is a key in the extras file, so it reads offline."""
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


UNKNOWN_CAUTION_LINE = "caution: unknown, the level could not be read"  # hooks/session_start.sh prints the same line when the read fails


def describe_caution(root):
    """The text `layout.py caution` prints, and session start prints: the level, its facts, its acts."""
    found = caution(root)
    first = UNKNOWN_CAUTION_LINE if found["level"] == "unknown" else "caution: " + found["level"]
    return "\n".join([first] + ["fact: " + f for f in found["facts"]]
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


# ---------------------------------------------------------------------------- mockup homes
#
# Decision mockup-home. A mockup that a waiting item or a roadmap step names is a repo path under the design folder,
# and version control holds it. This is the one home of the path (rule building-allow-list-is-the-constant): the guard
# (hooks/question_form.py) and the roadmap build (skills/roadmap/build.py) import it and keep no copy. That origin holds
# the file is the build's check (build.py mockup_on_origin); the guard judges shape only.
URL_FORM = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
WIN_DRIVE = re.compile(r"^[A-Za-z]:")


def _owner_home(home):
    """`home` as text, else this machine's home read now (HOME), else None when it cannot be told."""
    found = str(home) if home is not None else os.path.expanduser("~")
    return None if found in ("", "~") else found


def mockup_homes(root):
    """The folders a mockup may sit in, as a tuple of paths: the repo's design folder inside the checkout. Reads no
    file and starts no process."""
    return (os.path.join(root, *path(root, "design").split("/")),)


def mockup_home_words(root):
    """The mockup home as a sentence shows it, with no absolute path."""
    return "%s/<file>, committed to git" % path(root, "design")


def _flavour(*texts):
    """ntpath when any text is a Windows form (a drive letter or a backslash), else posixpath."""
    return ntpath if any(t and (WIN_DRIVE.match(t) or "\\" in t) for t in texts) else posixpath


def _parts(mod, text):
    """The parts of `text` with `.` and `..` folded out, in `mod`'s form. A `..` that escapes the start stays."""
    return tuple(part for part in re.split(r"[\\/]+", mod.normpath(text)) if part and part != ".")


def _is_absolute(mod, text):
    return bool(WIN_DRIVE.match(text)) or text.startswith(("/", "\\")) or mod.isabs(text)


def _below(parts, home, fold):
    """The parts of `parts` below `home` (both tuples of parts), or None when `parts` is not strictly below it."""
    head = parts[:len(home)]
    same = [p.casefold() for p in head] == [p.casefold() for p in home] if fold else head == home
    return parts[len(home):] if same and len(parts) > len(home) else None


def mockup_file(root, file, home=None):
    """(path, why) for a mockup `file`. path is the file as this machine reads it (`~` expanded, a relative file
    joined to `root`, `.` and `..` folded) when it sits under the design folder. Else path is None and why is
    "empty" (no file), "url", "folder" (the text ends in a slash) or "outside". A Windows form reads in any case, with
    either slash. Starts no process."""
    if not isinstance(file, str) or not file.strip():
        return None, "empty"
    file = file.strip()
    if URL_FORM.match(file):
        return None, "url"
    if file.endswith(("/", "\\")):
        return None, "folder"
    design = mockup_homes(root)[0]
    owner = _owner_home(home)
    mod = _flavour(file, owner)
    if file == "~" or file.startswith(("~/", "~\\")):
        if owner is None:
            return None, "outside"
        file = mod.join(owner, file[2:])
    elif not _is_absolute(mod, file):
        file = mod.join(root, file)
    if _below(_parts(mod, file), _parts(mod, design), mod is ntpath) is not None:
        return mod.normpath(file), None
    return None, "outside"


def mockup_home_problem(root, file, home=None):
    """None when `file` sits in the design folder of the repo at `root`, else one sentence that says why not and
    names the folder. The guard prints it, so it holds no absolute path."""
    found, why = mockup_file(root, file, home)
    if found:
        return None
    cause = {"empty": "has no file", "url": "is a link, and a link does not stay with the repo",
             "folder": "is a folder, and a folder holds no mockup"}.get(
        why, "is outside the design folder")
    return "the design's `file` %s. Keep the mockup in %s, and put its path in `file`." % (cause, mockup_home_words(root))


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
    # python3 lint/layout.py artifacts <root>: the repo's artifact registry as JSON, [] when none.
    # python3 lint/layout.py set-waiting-page <root> <url>: write the key once into the extras file of
    # <root>. Exit 0 wrote it; 1 already set (prints the URL); 2 bad URL or unreadable or unwritable file.
    ROOT_VERBS = (WAITING_PAGE, "devices", "caution", SHARED_RESOURCES, ARTIFACTS)
    if len(sys.argv) == 4 and sys.argv[1] == "set-waiting-page":
        try:
            here = os.path.abspath(sys.argv[2])
            if set_waiting_page(here, sys.argv[3]):
                sys.exit(0)
            print(waiting_page(here))
            sys.exit(1)
        except (LayoutError, OSError) as err:
            print("layout: %s" % err, file=sys.stderr)
            sys.exit(2)
    if not (len(sys.argv) == 4 and sys.argv[1] == "path" or len(sys.argv) == 3 and sys.argv[1] in ROOT_VERBS):
        sys.exit("usage: layout.py path <root> <kind> | layout.py waiting-page|devices|caution|shared-resources|artifacts <root> | layout.py set-waiting-page <root> <url>")
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
        elif sys.argv[1] == ARTIFACTS:
            print(json.dumps(artifacts(here)))
        else:
            print(path(here, sys.argv[3]))
    except (LayoutError, KeyError) as err:
        sys.exit("layout: %s" % err)
