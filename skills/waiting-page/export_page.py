#!/usr/bin/env python3
"""Copy the waiting page's database into the repo, and build it back (skill waiting-page, decision waiting-data-in-repo).

Export, the writer's step at each wake and before each republish:

    python3 ~/.claude/skills/waiting-page/export_page.py --fetched DIR --out WAITING_DIR [--page FETCHED.html]

DIR holds `<collection>/<doc_id>.json` for each of the five collections, as `ArtifactData list ... out_dir=DIR`
saves them; an empty collection is an empty folder. A script cannot call that tool, so the session fetches first.
WAITING_DIR is the `waiting-data` folder of the record branch (`layout.py path <root> waiting-data`). With --page,
the page's designData block lands in `page/designData.json`. The script never runs git: the session commits.

Verdict, one line, then exit:
  changed N  N files written or deleted in WAITING_DIR; exit 0
  same       nothing differs; exit 0
  refused    a value or key has the shape of a secret or of personal data; one line per find (file, JSON path,
             kind, never the value); nothing is written; exit 1
  unknown    a collection folder is missing, a file is not one JSON doc, or the page has no or two designData
             blocks; nothing is written; exit 2
Every doc is scanned, as parsed JSON, before the first write. Only the shape counts: words such as "token budget"
or "password manager" pass. A personal fact in plain words passes too.
A doc is written with sorted keys, two-space indent and a final newline, so an unchanged doc is byte-identical. A doc no
longer fetched is deleted from its collection folder; a truncated fetch deletes docs, and git history keeps them.

Rebuild, the recovery path. It reads only the repo copy, never the live page:

    python3 ~/.claude/skills/waiting-page/export_page.py --rebuild WAITING_DIR --batches OUT_DIR

Writes OUT_DIR/batch-NNN.json, each a JSON list of at most 50 `{op: "set", collection, doc_id, data}` entries,
one per doc in WAITING_DIR except `page/`, and prints `batches K docs N`. The session sends each list as an
`ArtifactData batch`. A missing or empty WAITING_DIR is `unknown`, exit 2.

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

COLLECTIONS = ("items", "answers", "groups", "asks", "meta")
PAGE_FOLDER, DESIGN_FILE = "page", "designData.json"
BATCH_SIZE = 50
REFUSED, UNKNOWN = 1, 2

# Each shape is a token or a value that names a person or opens an account. The lookbehinds keep a match
# from starting inside a longer word ("risk-" is not "sk-").
SECRET_SHAPES = (
    ("github-token", re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("api-key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("aws-key-id", re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])")),
    ("slack-token", re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]+")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")),
    ("auth-header", re.compile(r"\bAuthorization:\s*(?:Bearer|Basic)\s+\S+", re.I)),
    ("cookie-header", re.compile(r"\bCookie:\s*[^\s=;]+=\S+", re.I)),
    ("password", re.compile(r"\b(?:password|passwd|pwd)=\S+", re.I)),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
)
PHONE_RUN = re.compile(r"(?<![\w+(])\+?\(?\d[\d()\s.\-]{8,}\d(?!\w)")
DATE_START = re.compile(r"\d{4}-\d{2}-\d{2}")


class Stop(Exception):
    """The run ends with a verdict and a code, and has written nothing."""

    def __init__(self, verdict, code):
        super().__init__(verdict)
        self.code = code


def is_phone(run, after):
    """True when digit run `run`, followed by the text `after`, reads as a phone number. A date or a time ("2026-11-02 11:04"
    is ten digits in one run), a run of single digits (a viewBox, points) and a run with no group of three digits do not."""
    groups = re.findall(r"\d+", run)
    if sum(len(g) for g in groups) < 10 or DATE_START.match(run) or re.match(r":\d", after):
        return False
    return all(len(g) >= 2 for g in groups[1:]) and any(len(g) >= 3 for g in groups)


def kinds_in(text):
    """The kinds of secret or personal data that `text` has the shape of, each once."""
    found = [name for name, shape in SECRET_SHAPES if shape.search(text)]
    if any(is_phone(m.group(0), text[m.end():]) for m in PHONE_RUN.finditer(text)):
        found.append("phone")
    return found


def plain_key(key):
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def scan(node, path, out):
    """Append (path, kind) to `out` for each string value and each key of the parsed JSON `node`. The path of a find in a key
    names that key as <redacted>, so a find's line never holds its value."""
    if isinstance(node, str):
        out.extend((path, kind) for kind in kinds_in(node))
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
    """{doc_id: parsed JSON} of the `<doc_id>.json` files in `folder`. Anything else in it is unknown: a doc that
    is skipped would be deleted from the copy as if it were gone."""
    found = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not (os.path.isfile(path) and name.endswith(".json") and len(name) > len(".json")):
            raise Stop("unknown - %s/%s is not a <doc_id>.json file" % (label, name), UNKNOWN)
        found[name[:-len(".json")]] = load_json(path, "%s/%s" % (label, name))
    return found


def design_data(page_path):
    """The parsed JSON of the one designData block of the page at `page_path`."""
    try:
        with open(page_path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as err:
        raise Stop("unknown - the page cannot be read (%s)" % type(err).__name__, UNKNOWN)
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


def refuse(finds):
    for label, path, kind in finds:
        print("%s %s %s" % (label, path, kind))
    raise Stop("refused - %d find(s)" % len(finds), REFUSED)


def existing(out):
    """{relative path: bytes} of each doc file the copy holds in a collection folder."""
    found = {}
    for name in COLLECTIONS:
        folder = os.path.join(out, name)
        if os.path.isdir(folder):
            for file in os.listdir(folder):
                if file.endswith(".json"):
                    with open(os.path.join(folder, file), "rb") as handle:
                        found["%s/%s" % (name, file)] = handle.read()
    return found


def export(fetched, out, page):
    want = {}
    finds = []
    for name in COLLECTIONS:
        folder = os.path.join(fetched, name)
        if not os.path.isdir(folder):
            raise Stop("unknown - the fetched folder has no %s folder" % name, UNKNOWN)
        for doc_id, data in docs_in(folder, name).items():
            label = "%s/%s.json" % (name, doc_id)
            found = []
            scan(data, "$", found)
            finds.extend((label, path, kind) for path, kind in found)
            want[label] = canonical(data)
    if page:
        data = design_data(page)
        found = []
        scan(data, "$", found)
        finds.extend(("%s/%s" % (PAGE_FOLDER, DESIGN_FILE), path, kind) for path, kind in found)
        want["%s/%s" % (PAGE_FOLDER, DESIGN_FILE)] = canonical(data)
    if finds:
        refuse(finds)  # before any write, so a refused run leaves the copy as it was

    have = existing(out)
    if page:
        path = os.path.join(out, PAGE_FOLDER, DESIGN_FILE)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                have["%s/%s" % (PAGE_FOLDER, DESIGN_FILE)] = handle.read()
    changed = 0
    for label, text in want.items():
        if have.get(label) != text.encode("utf-8"):
            target = os.path.join(out, *label.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            changed += 1
    for label in have:
        if label not in want:
            os.remove(os.path.join(out, *label.split("/")))
            changed += 1
    return "changed %d" % changed if changed else "same"


def rebuild(waiting, batches):
    entries = []
    if os.path.isdir(waiting):
        for name in sorted(os.listdir(waiting)):
            folder = os.path.join(waiting, name)
            if name != PAGE_FOLDER and os.path.isdir(folder):
                for doc_id, data in docs_in(folder, name).items():
                    entries.append({"op": "set", "collection": name, "doc_id": doc_id, "data": data})
    if not entries:
        raise Stop("unknown - %s holds no docs" % waiting, UNKNOWN)
    os.makedirs(batches, exist_ok=True)
    pieces = [entries[i:i + BATCH_SIZE] for i in range(0, len(entries), BATCH_SIZE)]
    for number, piece in enumerate(pieces, 1):
        with open(os.path.join(batches, "batch-%03d.json" % number), "w", encoding="utf-8", newline="") as handle:
            handle.write(canonical(piece))
    return "batches %d docs %d" % (len(pieces), len(entries))


def main(argv):
    ap = argparse.ArgumentParser(description="Copy the waiting page's database into the repo, or build batches back from it.")
    ap.add_argument("--fetched", help="the folder `ArtifactData list` saved, one folder per collection")
    ap.add_argument("--out", help="the waiting-data folder to mirror into")
    ap.add_argument("--page", help="the fetched page.html, for its designData block")
    ap.add_argument("--rebuild", help="the waiting-data folder to read batches from")
    ap.add_argument("--batches", help="the folder to write batch-NNN.json into")
    args = ap.parse_args(argv)
    export_mode, rebuild_mode = bool(args.fetched or args.out or args.page), bool(args.rebuild or args.batches)
    if export_mode == rebuild_mode or (export_mode and not (args.fetched and args.out)) \
            or (rebuild_mode and not (args.rebuild and args.batches)):
        ap.error("use --fetched DIR --out DIR [--page FILE], or --rebuild DIR --batches DIR")
    try:
        verdict = export(args.fetched, args.out, args.page) if export_mode else rebuild(args.rebuild, args.batches)
    except Stop as stop:
        print(str(stop))
        return stop.code
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
