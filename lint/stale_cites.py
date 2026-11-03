#!/usr/bin/env python3
"""The stale-prose merge check. Standard library only.

    python3 lint/stale_cites.py --range <base>...<head>
    python3 lint/stale_cites.py --tree [REV]

Refuses a range that leaves a tracked Markdown line naming a name the range removed.
  STALE001  the line names a path the range deleted or renamed, and the path is absent at head.
            A rename names its new home.
  STALE002  the line cites `<file.py> <name>` as "`file.py` `name`" or "(file.py name)", and `name` was a
            def or class in that file at base (read with `ast`) and is not one at head. A name counts
            when it is module-level (also under a module-level if or try) or a def directly in a
            module-level class.
A line already stale at base, for a name the range did not remove, never fires. Left out: docs/records.md,
each file `.ste-lint-exclude` (and the EXCLUDE env of the ste-lint action) names, and a line marked
`<!-- ste-disable-line STALE001 -->` (or STALE002, STALE003, STALE004). Fenced blocks count as prose.
Each Markdown file is read as committed at head, never from the working tree.
--tree [REV] reads every tracked Markdown file at REV (default HEAD) instead of a range, so it fires on lines no
change touched. It is opt-in (the ste-lint input `tree-cites`). It needs no base, so a shallow clone is fine.
  STALE003  the line names `<folder>/.../<file.ext>` that is no tracked file (or folder) at REV, as written or
            from the folder of the Markdown file. One tracked file with the same name elsewhere is named as a
            hint. A cite with a placeholder character, no extension, no folder part, or a first segment that is
            no tracked top folder is no path cite, so it never fires.
  STALE004  the line anchors `path:N` or `path:N-M` on a tracked file, and N is below 1, M is below N, or the
            last number is past the file's last line. A dead path gives STALE003 only.
--tree and --range are exclusive.

Output: `path:line: CODE message`, then `stale-cites: PASS` or `stale-cites: FAIL`. Exit 0 pass, 1 findings,
2 a read that could not run, except a base that does not resolve (a shallow clone): that prints
`stale-cites: unknown, ...` naming fetch-depth 0 and exits 0, so a repo that pins the ste-lint action and
checks out shallow is not red at its pin move. A touched .py that does not parse at base or head is unknown
the same way: `stale-cites: unknown, <file> ...`, and it alone never makes the exit non-zero.

Cost, per ste-lint changed-scope run (CostTests in lint/test_stale_cites.py proves it): one python3 start.
Git starts 3 (rev-parse, merge-base, diff) when the range removes or renames no path and touches no .py.
A touched .py adds one `git cat-file --batch`. A removed path or def adds `ls-tree` and that `cat-file
--batch`, so 5 at most. Each tracked .md is read once, only when something was removed. It writes no file
(no .pyc either) and leaves no process running.
A --tree run starts one python3, then git rev-parse, ls-tree and one cat-file --batch (it reads each tracked .md
and each file a line anchor names, once). It writes no file.
"""
import argparse
import ast
import os
import posixpath
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # the cost contract: a run writes no file, so no .pyc for the import below
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

RECORDS_PAGE = "docs/records.md"
RUN = r"[\w./@+~-]+"  # a run of path characters; a cite is one whole run, so a `-` or `.` before a path is no boundary
NOT_BEFORE = r"(?<![\w/.@+~-])"
RUN_RE = re.compile(RUN)
PAIR_RES = (  # "`file.py` `name`" and "(file.py name)"
    re.compile(NOT_BEFORE + r"`?(%s\.py)`?\s+`([A-Za-z_]\w*)`" % RUN),
    re.compile(r"\(`?(%s\.py)`?\s+([A-Za-z_]\w*)(?:\(\))?\)" % RUN),
)
DISABLE_RE = re.compile(r"<!--\s*ste-disable-line([^>]*?)-->")
SIMPLE_PATH = re.compile(r"^%s$" % RUN)
FILE_CITE = re.compile(r"^[^/]+(?:/[^/]+)*/[^/]*[^/.]\.[A-Za-z0-9]+$")  # a folder part and an extension
ANCHOR = re.compile(r":(\d+)(?:-(\d+))?(?!\w)")


class Unknown(Exception):
    """A read that could not run."""


class BaseUnknown(Unknown):
    """The base of the range does not resolve, as in a shallow clone. Not a finding."""


def git(*args, on_fail=Unknown):
    done = _nowindow.run(["git", *args], capture_output=True)
    if done.returncode != 0:
        raise on_fail("git %s failed: %s" % (" ".join(args[:2]), done.stderr.decode("utf-8", "replace").strip()))
    return done.stdout


class BlobReader:
    """One `git cat-file --batch` process for every blob read."""

    def __init__(self):
        self.proc = None

    def get(self, spec):
        """Bytes of the blob, or None when the object does not exist."""
        if self.proc is None:
            self.proc = _nowindow.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.proc.stdin.write(spec.encode("utf-8") + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if not header:
            raise Unknown("git cat-file ended early")
        if header[-1] == b"missing":
            return None
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return data if header[1] == b"blob" else b""

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait()


def glob_regex(pattern):
    """A .ste-lint-exclude pathspec as a regex, read as git reads `:(exclude,glob)<pattern>`: `**/` spans
    zero or more folders, `*` stays in one. A pattern with no wildcard also matches each file under it as a
    folder, so `vendor` and `vendor/` leave out `vendor/a.md`. A wildcard pattern matches the whole path only."""
    literal = not any(c in pattern for c in "*?[")
    if literal:
        pattern = pattern.rstrip("/")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + (r"(?:/.*)?\Z" if literal else r"\Z"))


def exclude_patterns(root):
    lines = []
    try:
        with open(os.path.join(root, ".ste-lint-exclude"), encoding="utf-8") as f:
            lines += f.read().splitlines()
    except OSError:
        pass
    lines += os.environ.get("EXCLUDE", "").replace(",", "\n").splitlines()
    cleaned = (line.strip() for line in lines)
    return [glob_regex(p) for p in cleaned if p and not p.startswith("#")]


def parse_range(text):
    """(diff arguments, base spec, head spec). A three-dot range reads base blobs at the merge base."""
    if "..." in text:
        left, right = text.split("...", 1)
        base = git("merge-base", left, right, on_fail=BaseUnknown).decode().strip()
        return [text], base, right
    if ".." in text:
        left, right = text.split("..", 1)
        return [text], left, right
    raise Unknown("--range wants base...head, got %r" % text)


def changed_paths(diff_args):
    """(removed, renamed, modified): removed paths, {old: new}, and paths changed in place."""
    tokens = git("diff", "-M", "--name-status", "-z", *diff_args, on_fail=BaseUnknown).decode("utf-8", "replace").split("\0")
    removed, renamed, modified = [], {}, []
    i = 0
    while i < len(tokens) and tokens[i]:
        status = tokens[i][0]
        if status == "R" or status == "C":
            if status == "R":
                renamed[tokens[i + 1]] = tokens[i + 2]
            i += 3
            continue
        if status == "D":
            removed.append(tokens[i + 1])
        elif status == "M":
            modified.append(tokens[i + 1])
        i += 2
    return removed, renamed, modified


def defs_in(source):
    """Names a prose line can cite: each module-level def and class (also under a module-level if or try),
    and each def directly in a module-level class. A def nested in a function is no public name. Read with
    `ast`; None when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    names = set()

    def collect(body, into_classes):
        for node in body:
            if isinstance(node, kinds):
                names.add(node.name)
                if isinstance(node, ast.ClassDef) and into_classes:
                    collect(node.body, False)
            else:
                for field in ("body", "orelse", "finalbody"):
                    collect(getattr(node, field, None) or [], into_classes)
                for handler in getattr(node, "handlers", None) or []:
                    collect(handler.body, into_classes)

    collect(tree.body, True)
    return names


def disabled(line):
    codes = set()
    for match in DISABLE_RE.finditer(line):
        codes.update(re.split(r"[\s,:]+", match.group(1).strip()))
    return codes


def path_cites(line, gone, exotic):
    """Each removed path the line names, at a path boundary."""
    hits = []
    for run in RUN_RE.finditer(line):
        text = run.group(0)
        candidate = text.rstrip(".-")
        if candidate in gone and candidate not in hits:
            hits.append(candidate)
    for path in exotic:
        if re.search(NOT_BEFORE + r"%s(?![\w/]|[.-]\w)" % re.escape(path), line) and path not in hits:
            hits.append(path)
    return hits


def tracked_entries(rev):
    """[(mode, path)] of every entry in the tree at rev."""
    tree = git("ls-tree", "-r", "-z", rev).decode("utf-8", "replace").split("\0")
    return [(e.split(" ", 1)[0], e.split("\t", 1)[1]) for e in tree if "\t" in e]


def markdown_files(entries, excludes):
    """The tracked .md files a prose check reads: regular files, not the records page, not excluded."""
    return [p for mode, p in entries if mode in ("100644", "100755") and p.endswith(".md")
            and p != RECORDS_PAGE and not any(rx.match(p) for rx in excludes)]


def read_markdown(batch, rev, md):
    blob = batch.get("%s:%s" % (rev, md))
    if blob is None:
        raise Unknown("%s is in the tree at %s but cannot be read" % (md, rev))
    return blob.decode("utf-8", "replace").replace("\r\n", "\n")  # a bad byte is U+FFFD, never a skip


def scan(range_text):
    """(found, unknowns): {(path, line, code): [messages]}, and one text per touched .py that does not parse."""
    diff_args, base, head = parse_range(range_text)
    removed, renamed, modified = changed_paths(diff_args)
    found, unknowns = {}, []
    py_files = {p: p for p in modified if p.endswith(".py")}
    py_files.update({old: new for old, new in renamed.items() if old.endswith(".py") and new.endswith(".py")})
    if not removed and not renamed and not py_files:
        return found, unknowns  # the cost contract: nothing removed, so no blob, tree or Markdown read
    batch = BlobReader()
    try:
        gone = {}  # path -> new home or None
        for path in removed + list(renamed):
            if batch.get("%s:%s" % (head, path)) is None:
                gone[path] = renamed.get(path)
        simple = {p for p in gone if SIMPLE_PATH.match(p)}
        exotic = [p for p in gone if p not in simple]

        removed_names = {}  # file at base -> names the range removed
        for path in sorted(py_files):
            old_src = batch.get("%s:%s" % (base, path))
            new_src = batch.get("%s:%s" % (head, py_files[path]))
            before = defs_in(old_src) if old_src is not None else None
            after = defs_in(new_src) if new_src is not None else None
            bad = [side for side, names in (("base", before), ("head", after)) if names is None]
            if bad:
                unknowns.append("%s does not parse at %s; the defs it removed were not checked"
                                % (path, " and ".join(bad)))
            elif before - after:
                removed_names[path] = before - after
        if not gone and not removed_names:
            return found, unknowns

        for md in markdown_files(tracked_entries(head), exclude_patterns(".")):
            text = read_markdown(batch, head, md)
            for number, line in enumerate(text.split("\n"), 1):
                off = disabled(line) if "ste-disable-line" in line else set()
                cited = path_cites(line, simple, exotic) if gone and "STALE001" not in off else []
                for path in cited:
                    home = gone[path]
                    text = ("%s was renamed to %s in this range; name the new home" % (path, home) if home
                            else "%s was deleted in this range" % path)
                    found.setdefault((md, number, "STALE001"), []).append(text)
                if removed_names and ".py" in line and "STALE002" not in off:
                    for pair in PAIR_RES:
                        for match in pair.finditer(line):
                            path, name = match.group(1), match.group(2)
                            if path not in cited and name in removed_names.get(path, ()):
                                found.setdefault((md, number, "STALE002"), []).append(
                                    "%s no longer defines %s at head; find its new home" % (path, name))
    finally:
        batch.close()
    return found, unknowns


def placeholder_adjacent(line, start, end):
    """A run touching a glob, template or shell-variable character names no one file. A `*` before the run is
    Markdown emphasis (`**path**`), so only a lone `*` after it counts."""
    before = line[start - 1] if start else ""
    after = line[end] if end < len(line) else ""
    return bool(before and before in "${") or bool(after and after in "?<{[$") or (after == "*" and before != "*")


def line_count(data):
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def scan_tree(rev):
    """(found, unknowns) for every tracked Markdown line at rev: STALE003 dead path cites, STALE004 bad anchors."""
    found = {}
    entries = tracked_entries(rev)
    files = {p for _, p in entries}
    folders = {p.rsplit("/", i)[0] for p in files for i in range(1, p.count("/") + 1)}
    tops = {p.split("/", 1)[0] for p in files if "/" in p}
    by_name = {}
    for p in sorted(files):
        by_name.setdefault(p.rsplit("/", 1)[-1], []).append(p)
    mds = markdown_files(entries, exclude_patterns("."))
    batch = BlobReader()
    counts = {}  # tracked file -> its line count, read once

    def lines_of(path):
        if path not in counts:
            data = batch.get("%s:%s" % (rev, path))
            counts[path] = line_count(data) if data is not None else None
        return counts[path]

    try:
        for md in mds:
            folder = posixpath.dirname(md)
            for number, line in enumerate(read_markdown(batch, rev, md).split("\n"), 1):
                if "/" not in line:
                    continue
                off = disabled(line) if "ste-disable-line" in line else set()
                for run in RUN_RE.finditer(line):
                    cite = run.group(0).rstrip(".-")
                    if not FILE_CITE.match(cite) or cite.split("/", 1)[0] not in tops \
                            or placeholder_adjacent(line, run.start(), run.end()):
                        continue
                    home = next((c for c in (cite, posixpath.normpath(posixpath.join(folder, cite)))
                                 if c in files or c in folders), None)
                    if home is None:
                        if "STALE003" not in off:
                            same = by_name.get(cite.rsplit("/", 1)[-1], [])
                            hint = " (did you mean %s?)" % same[0] if len(same) == 1 else ""
                            found.setdefault((md, number, "STALE003"), []).append(
                                "%s names no tracked file at %s%s" % (cite, rev, hint))
                        continue
                    anchor = ANCHOR.match(line, run.end()) if cite == run.group(0) and home in files else None
                    if anchor is None or "STALE004" in off:
                        continue
                    first, last = int(anchor.group(1)), int(anchor.group(2) or anchor.group(1))
                    total = lines_of(home)
                    if total is not None and (first < 1 or last < first or last > total):
                        found.setdefault((md, number, "STALE004"), []).append(
                            "%s%s is not a line of that file, which has %d" % (home, anchor.group(0), total))
    finally:
        batch.close()
    return found, []


def main(argv):
    parser = argparse.ArgumentParser(description="Refuse Markdown lines that name what no longer exists.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--range", help="base...head, as the ste-lint step diffs")
    mode.add_argument("--tree", nargs="?", const="HEAD", metavar="REV",
                      help="every tracked Markdown line at REV (default HEAD): dead paths, bad line anchors")
    args = parser.parse_args(argv)
    try:
        root = git("rev-parse", "--show-toplevel").decode().strip()
        os.chdir(root)
        found, unknowns = scan(args.range) if args.range else scan_tree(args.tree)
    except BaseUnknown as exc:
        print("stale-cites: unknown, the base of %s does not resolve (%s). Check out with fetch-depth 0 "
              "(actions/checkout) so the range has history. Nothing was checked." % (args.range, exc))
        return 0
    except (Unknown, OSError) as exc:
        print("stale-cites: UNKNOWN, %s" % exc)
        return 2
    for (path, number, code), texts in sorted(found.items()):
        print("%s:%d: %s %s" % (path, number, code, "; ".join(texts)))
    for text in unknowns:
        print("stale-cites: unknown, %s" % text)
    print("stale-cites: %s" % ("FAIL, %d finding(s)" % len(found) if found else "PASS"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
