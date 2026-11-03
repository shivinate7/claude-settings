#!/usr/bin/env python3
"""Copy an artifact's page, its files and its database into the repo, and build the database back (skill waiting-page, decision waiting-data-in-repo).

Export, the writer's step at each wake and before each republish:

    python3 ~/.claude/skills/waiting-page/export_page.py --fetched DIR --out WAITING_DIR [--page FETCHED.html]
        [--allow-empty COLLECTION]

DIR holds `<collection>/<doc_id>.json` for each of the five collections, as `ArtifactData list ... out_dir=DIR`
saves them; an empty collection is an empty folder. A script cannot call that tool, so the session fetches first.
The session touches `.complete` in each collection folder after the last list page, so a fetch that stopped early
shows: a collection with no marker is unknown. A collection that is empty now while the copy holds docs of it is
unknown too, unless the session names it with --allow-empty.
WAITING_DIR is the `waiting-data` folder of the record branch (`layout.py path <root> waiting-data`). With --page,
the page's bytes land in `page/page.html`, and its designData block in `page/designData.json`. A file is written
only when its bytes differ. The script never runs git: the session commits.

Verdict, one line, then exit:
  changed N  N files written or deleted in WAITING_DIR; exit 0
  same       nothing differs; exit 0
  refused    a value or key has the shape of a secret or of personal data; one line per find (file, JSON path,
             kind, never the value); nothing is written; exit 1
  unknown    a collection folder or its marker is missing, a file is not one JSON doc, a collection emptied, or the
             page has no or two designData blocks; nothing is written; exit 2
  unknown    the run crashed (one line, nothing written); exit 3
Every doc is scanned, as parsed JSON, before the first write: each string value, each key, each doc id and each
10 or 11 digit number (a phone). The page text and each supporting text file are scanned as text with the same
shapes, except that a version pin such as `react@18.3.1` is not an email; a file that is not UTF-8 is binary and not
scanned. Only the shape counts: words such as "token budget" or "password manager" pass.
A personal fact in plain words passes too.
A doc is written with sorted keys, two-space indent and a final newline, so an unchanged doc is byte-identical. A doc no
longer fetched is deleted from its collection folder; a truncated fetch deletes docs, and git history keeps them.

Rebuild, the recovery path. It reads only the repo copy, never the live page:

    python3 ~/.claude/skills/waiting-page/export_page.py --rebuild WAITING_DIR --batches OUT_DIR

Writes OUT_DIR/batch-NNN.json, each a JSON list of at most 50 `{op: "set", collection, doc_id, data}` entries and
under 900,000 bytes, one entry per doc in WAITING_DIR except `page/`, and prints `batches K docs N`. The session
sends each list as an `ArtifactData batch`. Unknown, exit 2: a missing or empty WAITING_DIR, a folder in it that is
neither one of the five collections nor `page/`, or one doc over the byte cap.

Every artifact, the step "Before you switch Claude accounts":

    python3 ~/.claude/skills/waiting-page/export_page.py --all REPO_ROOT --fetched DIR --worktree RECORD_WORKTREE
        [--allow-empty COLLECTION]

REPO_ROOT holds the extras file with the artifacts registry (lint/layout.py `artifacts()`). DIR holds one folder per
artifact id, each laid out as in a single export, plus `page.html` and `files/<path>` (the page's supporting files).
Each entry exports the collections it lists to its export path under RECORD_WORKTREE (the waiting page: the
waiting-data folder; any other artifact: `artifacts/<id>/`), with the same scan and mirror as one export. Any role's
`<id>/page.html` lands at `page/page.html` there, and `<id>/files/<path>` at `page/files/<path>`; a waiting-page entry
also exports its designData block. A supporting file no longer fetched stays in the copy; history is the delete.
Each artifact prints one line `<id>: <verdict>`, and a find's lines start with `<id>:` too. One artifact's refusal or
unknown leaves its own folder as it was and holds back no other. Exit: 0 when every artifact is changed or same; else
the worst of 1 (refused), 2 (unknown: also a registry that is missing, empty or unreadable) and 3 (a crash).

Cost: one python process, one read of each file, writes only for a changed doc. No git, no network, no timer.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import splice  # noqa: E402  the one home of the designData block's span

# The same five as lint/layout.py WAITING_COLLECTIONS. A copy, because a single export and the rebuild must run with no
# lint/ beside them: the recovery path may not depend on the repo it recovers (verification-recovery-independent-of-state).
COLLECTIONS = ("items", "answers", "groups", "asks", "meta")
PAGE_FOLDER, DESIGN_FILE, PAGE_FILE, FILES_FOLDER = "page", "designData.json", "page.html", "files"
MARKER = ".complete"  # the session touches it in a collection folder after the last list page
BATCH_SIZE = 50
BATCH_BYTES = 900000  # one ArtifactData batch call stays under about 1 MB
REFUSED, UNKNOWN, CRASH = 1, 2, 3

# Each shape is a token or a value that names a person or opens an account. The lookbehinds keep a match
# from starting inside a longer word ("risk-" and "btn-sk-" are not "sk-").
SECRET_SHAPES = (
    ("github-token", re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("api-key", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")),
    ("stripe-key", re.compile(r"(?<![A-Za-z0-9_-])[sr]k_live_[A-Za-z0-9]{16,}")),
    ("google-key", re.compile(r"(?<![A-Za-z0-9_-])AIzaSy[A-Za-z0-9_-]{33}")),
    ("gitlab-token", re.compile(r"(?<![A-Za-z0-9_-])glpat-[A-Za-z0-9_-]{20,}")),
    ("aws-key-id", re.compile(r"(?<![A-Z0-9])A[KS]IA[A-Z0-9]{16}(?![A-Z0-9])")),
    ("slack-token", re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]+")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")),
    ("auth-header", re.compile(r"\bAuthorization:\s*(?:Bearer|Basic)\s+\S+", re.I)),
    ("cookie-header", re.compile(r"\bCookie:\s*[^\s=;]+=\S+", re.I)),
    ("session-cookie", re.compile(r"(?<![A-Za-z0-9_.])connect\.sid=\S+")),
    ("url-secret", re.compile(r"[?&](?:access_token|key|sig|token)=[^&\s#]+", re.I)),
    ("password", re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_]*(?:password|passwd|pwd)[ \t]*[=:][ \t]*\S+", re.I)),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
)
# A phone in a string has a country code and separated groups, or the "(xxx) xxx-xxxx" form, or groups of 3, 3 and 4
# digits joined by one separator. A bare run of digits is never one: a PO number or a timestamp is not a phone.
PHONE_COUNTRY = re.compile(r"(?<![\w+])\+\d{1,3}[\s.\-]*\(?\d{1,4}\)?(?:[\s.\-]+\d{2,4}){1,4}(?!\d)")
PHONE_OTHER = (
    re.compile(r"(?<!\d)\(\d{3}\)\s*\d{3}[\s.\-]\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}([-. ])\d{3}\1\d{4}(?!\d)"),
)
VERSION_PIN = re.compile(r"@\d+(?:\.\d+)*(?![\w.-]*[A-Za-z])")  # `@18.3.1` in a CDN address
DATE_START = re.compile(r"\d{4}-\d{2}-\d{2}")
PHONE_DIGITS = (10, 11)  # a JSON number of this many digits is a phone; 13 digits is an epoch in milliseconds


class Stop(Exception):
    """The run ends with a verdict and a code, and has written nothing."""

    def __init__(self, verdict, code):
        super().__init__(verdict)
        self.code = code


def is_phone(text):
    """True when `text` holds a phone-shaped run. A country-code form with fewer than ten digits, or one that
    runs into an ISO date, is not a phone."""
    for found in PHONE_COUNTRY.finditer(text):
        whole = found.group(0)
        if sum(c.isdigit() for c in whole) >= 10 and not DATE_START.search(whole):
            return True
    return any(shape.search(text) for shape in PHONE_OTHER)


def kinds_in(text):
    """The kinds of secret or personal data that `text` has the shape of, each once."""
    found = [name for name, shape in SECRET_SHAPES if shape.search(text)]
    if is_phone(text):
        found.append("phone")
    return found


def plain_key(key):
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def scan(node, path, out):
    """Append (path, kind) to `out` for each string value, each key and each phone-length integer of the parsed JSON
    `node`. The path of a find in a key names that key as <redacted>, so a find's line never holds its value."""
    if isinstance(node, str):
        out.extend((path, kind) for kind in kinds_in(node))
    elif isinstance(node, int) and not isinstance(node, bool):
        if len(str(abs(node))) in PHONE_DIGITS:
            out.append((path, "phone"))
    elif isinstance(node, list):
        for number, child in enumerate(node):
            scan(child, "%s[%d]" % (path, number), out)
    elif isinstance(node, dict):
        for key, child in node.items():
            hit = kinds_in(key)
            here = "%s.%s" % (path, "<redacted>" if hit else plain_key(key))
            out.extend((here, kind) for kind in hit)
            scan(child, here, out)


def canonical(data):
    """The text a copy holds for `data`: sorted keys, two-space indent, a final newline."""
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as err:
        raise Stop("unknown - %s is not one JSON doc (%s)" % (label, type(err).__name__), UNKNOWN)


def docs_in(folder, label):
    """{doc_id: parsed JSON} of the `<doc_id>.json` files in `folder`. Anything but the marker is unknown: a doc that
    is skipped would be deleted from the copy as if it were gone."""
    found = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name == MARKER and os.path.isfile(path):
            continue
        if not (os.path.isfile(path) and name.endswith(".json") and len(name) > len(".json")):
            raise Stop("unknown - %s/%s is not a <doc_id>.json file" % (label, name), UNKNOWN)
        found[name[:-len(".json")]] = load_json(path, "%s/%s" % (label, name))
    return found


def read_page(page_path):
    """(bytes, text) of the page at `page_path`. The bytes are what lands in the copy; the text is what is scanned."""
    try:
        with open(page_path, "rb") as handle:
            raw = handle.read()
        return raw, raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise Stop("unknown - the page cannot be read (%s)" % type(err).__name__, UNKNOWN)


def design_data(text):
    """The parsed JSON of the one designData block in the page `text`."""
    try:
        start, end = splice.design_span(text, "the page")
    except SystemExit as err:
        raise Stop("unknown - %s" % str(err).replace(", so nothing was written.", ""), UNKNOWN)
    element = text[start:end]
    body = element[element.index(">") + 1:element.rindex("</")]
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("unknown - the page's designData block is not JSON", UNKNOWN)


def supporting_files(folder):
    """{relative path: bytes} of each file under `folder`, a page's supporting files; {} when there is none."""
    found = {}
    for here, _dirs, names in os.walk(folder):
        for name in names:
            with open(os.path.join(here, name), "rb") as handle:
                found[os.path.relpath(os.path.join(here, name), folder).replace(os.sep, "/")] = handle.read()
    return found


def scan_text(label, text, finds):
    """Append (label, "$", kind) to `finds` for each kind of find in `text`, a page or a supporting text file. A
    package version pin such as `react@18.3.1` is not an email: its domain has no letter."""
    text = VERSION_PIN.sub("@", text)
    finds.extend((label, "$", kind) for kind in kinds_in(text))


def refuse(finds, prefix=""):
    for label, path, kind in finds:
        print("%s%s %s %s" % (prefix, label, path, kind))
    raise Stop("refused - %d find(s)" % len(finds), REFUSED)


def existing(out, collections=COLLECTIONS):
    """{relative path: bytes} of each doc file the copy holds in a folder of `collections`."""
    found = {}
    for name in collections:
        folder = os.path.join(out, name)
        if os.path.isdir(folder):
            for file in os.listdir(folder):
                if file.endswith(".json"):
                    with open(os.path.join(folder, file), "rb") as handle:
                        found["%s/%s" % (name, file)] = handle.read()
    return found


def export(fetched, out, page, allow_empty, collections=COLLECTIONS, prefix="", design=True, files=None):
    docs = {}
    for name in collections:
        folder = os.path.join(fetched, name)
        if not os.path.isdir(folder):
            raise Stop("unknown - the fetched folder has no %s folder" % name, UNKNOWN)
        if not os.path.isfile(os.path.join(folder, MARKER)):
            raise Stop("unknown - %s has no %s marker, so the fetch may have stopped early" % (name, MARKER), UNKNOWN)
        docs[name] = docs_in(folder, name)

    have = existing(out, collections)
    for name in collections:
        kept = [label for label in have if label.startswith(name + "/")]
        if not docs[name] and kept and name not in allow_empty:
            raise Stop("unknown - %s is empty but the copy holds %d doc(s) of it; pass --allow-empty %s if it emptied"
                       % (name, len(kept), name), UNKNOWN)

    want = {}
    finds = []
    for name in collections:
        for doc_id, data in docs[name].items():
            hits = [("$id", kind) for kind in kinds_in(doc_id)]
            label = "%s/%s.json" % (name, "<redacted>" if hits else doc_id)
            scan(data, "$", hits)
            finds.extend((label, path, kind) for path, kind in hits)
            want["%s/%s.json" % (name, doc_id)] = canonical(data).encode("utf-8")
    if page:
        raw, text = read_page(page)
        label = "%s/%s" % (PAGE_FOLDER, PAGE_FILE)
        if design:
            data = design_data(text)
            found = []
            scan(data, "$", found)
            finds.extend(("%s/%s" % (PAGE_FOLDER, DESIGN_FILE), path, kind) for path, kind in found)
            want["%s/%s" % (PAGE_FOLDER, DESIGN_FILE)] = canonical(data).encode("utf-8")
        scan_text(label, text, finds)
        want[label] = raw
    for rel, raw in (files or {}).items():
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None  # a binary file has no text to scan
        hit = bool(kinds_in(rel))
        label = "%s/%s/%s" % (PAGE_FOLDER, FILES_FOLDER, "<redacted>" if hit else rel)
        finds.extend((label, "$name", kind) for kind in kinds_in(rel))
        if text is not None:
            scan_text(label, text, finds)
        want["%s/%s/%s" % (PAGE_FOLDER, FILES_FOLDER, rel)] = raw
    if finds:
        refuse(finds, prefix)  # before any write, so a refused run leaves the copy as it was

    changed = 0
    for label, raw in want.items():
        target = os.path.join(out, *label.split("/"))
        if label in have:
            old = have[label]
        elif os.path.isfile(target):  # the page and its files are not in a collection folder
            with open(target, "rb") as handle:
                old = handle.read()
        else:
            old = None
        if old != raw:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(raw)
            changed += 1
    for label in have:
        if label not in want:
            os.remove(os.path.join(out, *label.split("/")))
            changed += 1
    return "changed %d" % changed if changed else "same"


def export_all(root, fetched, worktree, allow_empty):
    """Export each registry artifact of the repo at `root`; print one line per artifact; the exit code."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
    sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
    import layout  # --all mode only: a single export and the rebuild run with no lint/ beside them
    try:
        entries = layout.artifacts(root)
    except layout.LayoutError as err:
        raise Stop("unknown - the artifacts registry cannot be read: %s" % err, UNKNOWN)
    if not entries:
        raise Stop("unknown - %s has no artifacts registry entry to export" % root, UNKNOWN)
    worst = 0
    for entry in entries:
        name = entry["id"]
        folder = os.path.join(fetched, name)
        page = os.path.join(folder, PAGE_FILE)
        files = os.path.join(folder, FILES_FOLDER)
        try:
            if not os.path.isdir(folder):
                raise Stop("unknown - the fetched folder has no %s folder" % name, UNKNOWN)
            verdict = export(folder, os.path.join(worktree, *entry["export"].split("/")),
                             page if os.path.isfile(page) else None, allow_empty, tuple(entry["collections"]), "%s: " % name,
                             entry["role"] == layout.WAITING_ROLE, supporting_files(files) if os.path.isdir(files) else None)
            code = 0
        except Stop as stop:
            verdict, code = str(stop), stop.code
        except Exception as err:  # one artifact's crash must not hide the verdict of the others
            verdict, code = "unknown - the run crashed (%s)" % type(err).__name__, CRASH
        print("%s: %s" % (name, verdict))
        worst = max(worst, code)
    return worst


def entry_bytes(entry):
    """The bytes `entry` takes inside a batch file, which is `canonical` of a list: two-space indent on each line."""
    text = json.dumps(entry, sort_keys=True, indent=2)
    return len(text) + 2 + 2 * text.count("\n")  # ensure_ascii is on, so a character is a byte


def batch_bytes(count, entries_total):
    """A batch file's size: "[\\n", the entries joined by ",\\n", "\\n]" and the final newline."""
    return 3 + 2 * count + entries_total


def rebuild(waiting, batches):
    entries = []
    if os.path.isdir(waiting):
        for name in sorted(os.listdir(waiting)):
            folder = os.path.join(waiting, name)
            if name == PAGE_FOLDER:
                continue
            if name not in COLLECTIONS or not os.path.isdir(folder):
                raise Stop("unknown - %s/%s is neither a collection folder nor %s/" % (waiting, name, PAGE_FOLDER), UNKNOWN)
            for doc_id, data in docs_in(folder, name).items():
                entries.append({"op": "set", "collection": name, "doc_id": doc_id, "data": data})
    if not entries:
        raise Stop("unknown - %s holds no docs" % waiting, UNKNOWN)

    pieces, piece, total = [], [], 0
    for entry in entries:
        size = entry_bytes(entry)
        if batch_bytes(1, size) >= BATCH_BYTES:
            raise Stop("unknown - %s/%s is over the %d byte batch cap" % (entry["collection"], entry["doc_id"], BATCH_BYTES), UNKNOWN)
        if piece and (len(piece) == BATCH_SIZE or batch_bytes(len(piece) + 1, total + size) >= BATCH_BYTES):
            pieces.append(piece)
            piece, total = [], 0
        piece.append(entry)
        total += size
    pieces.append(piece)

    os.makedirs(batches, exist_ok=True)
    for number, piece in enumerate(pieces, 1):
        with open(os.path.join(batches, "batch-%03d.json" % number), "w", encoding="utf-8", newline="") as handle:
            handle.write(canonical(piece))
    return "batches %d docs %d" % (len(pieces), len(entries))


def main(argv):
    ap = argparse.ArgumentParser(description="Copy the waiting page's database into the repo, or build batches back from it.")
    ap.add_argument("--fetched", help="the folder `ArtifactData list` saved, one folder per collection")
    ap.add_argument("--out", help="the waiting-data folder to mirror into")
    ap.add_argument("--page", help="the fetched page.html, for its designData block")
    ap.add_argument("--allow-empty", action="append", default=[], metavar="COLLECTION",
                    help="a collection that really emptied, so its docs leave the copy")
    ap.add_argument("--all", help="the repo root whose artifacts registry lists each artifact to export")
    ap.add_argument("--worktree", help="with --all: the record branch worktree each artifact's export path is under")
    ap.add_argument("--rebuild", help="the waiting-data folder to read batches from")
    ap.add_argument("--batches", help="the folder to write batch-NNN.json into")
    args = ap.parse_args(argv)
    all_mode = bool(args.all or args.worktree)
    export_mode, rebuild_mode = bool(args.out or args.page or (args.fetched and not all_mode)), bool(args.rebuild or args.batches)
    if [all_mode, export_mode, rebuild_mode].count(True) != 1 or (all_mode and not (args.all and args.fetched and args.worktree)) \
            or (export_mode and not (args.fetched and args.out)) or (rebuild_mode and not (args.rebuild and args.batches)):
        ap.error("use --fetched DIR --out DIR [--page FILE], or --all ROOT --fetched DIR --worktree DIR, or --rebuild DIR --batches DIR")
    if export_mode and any(name not in COLLECTIONS for name in args.allow_empty):
        ap.error("--allow-empty names one of: %s" % ", ".join(COLLECTIONS))
    try:
        if all_mode:
            return export_all(os.path.abspath(args.all), args.fetched, args.worktree, args.allow_empty)
        if export_mode:
            verdict = export(args.fetched, args.out, args.page, args.allow_empty)
        else:
            verdict = rebuild(args.rebuild, args.batches)
    except Stop as stop:
        print(str(stop))
        return stop.code
    except Exception as err:  # a crash is unknown, never a silent pass or a traceback the reader scrolls past
        print("unknown - the run crashed (%s)" % type(err).__name__)
        return CRASH
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
