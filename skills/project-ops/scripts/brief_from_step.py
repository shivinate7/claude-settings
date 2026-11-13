#!/usr/bin/env python3
"""Prints a lane brief for one roadmap step, filled into templates/brief.md. Standard library only.

    python3 brief_from_step.py SLUG [--repo DIR] [--ref REF] [--topic SLUG] [--cap N]

The step is roadmap/data/steps/SLUG.json at REF in DIR (default: the current folder at origin/roadmap). The rulings
are the store's entries (lint/ruled_store.py) whose step is SLUG, open or closed, plus each entry whose id or alias the
step note names. Each ruling prints with its quote word for word, its time and its source.

A step file has no field for files or a topic, and an optional `done_check` (text) and `ci_only` (true). The tool prints
a marker for each one missing, for the coordinator to fill, and invents nothing; `ci_only` adds `proved at batch CI`. Under Files it lists only the paths the step note names; it copies no other note text.
An absent or unreadable store prints `Rulings: unknown (store ...)`, never "no rulings".

Exit 0 with the brief on stdout; exit 1 when the step file is missing or unreadable; exit 2 on a bad argument.
Cost: the two git reads of ruled_store.read_store and one more cat-file --batch for the step. No file is written.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(HERE, "..", "..", "..", "lint"))
import ruled_store  # noqa: E402  the one reader of the ruled store

TEMPLATE = os.path.join(HERE, "..", "templates", "brief.md")  # the one template
FILES_MARKER = "<coordinator names the files>"
CHECK_MARKER = "<coordinator names the check that proves done>"
TOPIC_MARKER = "<topic-slug>"
PROVED = "proved at batch CI"  # the Done-check form for a check only batch CI can prove
CI_ONLY_LINE = "[ci_only] "  # a template line that prints only when the step sets ci_only
PARAPHRASE = "(paraphrase, no owner quote)"
DEFAULT_CAP = 25  # a brief with no cap named caps the report at 25 lines
# A file name in step-note text; the same shape the test reads as "a path".
PATH = re.compile(r"[\w./~-]+\.(?:py|md|json|sh|mjs|js|yml|yaml|html|txt|tmpl)\b")
FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class NoStep(Exception):
    """The step file is missing or is not a JSON object."""


def read_step(slug, repo, ref):
    if not ruled_store.STEP_SLUG.match(slug):
        raise NoStep("not a step slug: %s" % slug)
    spec = "%s:%s%s.json" % (ref, ruled_store.STEP_DIR, slug)
    blob = ruled_store._batch_blobs(repo, [spec]).get(spec)
    if blob is None:
        raise NoStep("no step file for %s at %s" % (slug, ref))
    try:
        step = json.loads(blob.decode("utf-8"))
    except ValueError:
        step = None
    if not isinstance(step, dict):
        raise NoStep("the step file for %s is not a JSON object" % slug)
    return step


def _names(entry):
    aliases = entry.get("aliases")
    listed = [a for a in aliases if isinstance(a, str)] if isinstance(aliases, list) else []
    return [n for n in [entry.get("id")] + listed if isinstance(n, str) and n]


def governing(entries, slug, note):
    """The entries for this step: its slug among the entry's steps, or an id or alias the note names as a whole word."""
    def named(name):
        return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), note) is not None
    return [e for e in entries if slug in ruled_store._steps_of(e) or any(named(n) for n in _names(e))]


def ruling_line(entry):
    quote = entry.get("quote")
    when = "%s, %s" % (entry.get("at", "?"), entry.get("source", "?"))
    mark = " [closed]" if entry.get("status") == "closed" else ""
    if isinstance(quote, str) and quote.strip():
        return '- %s%s: "%s" (%s)' % (entry.get("id", "?"), mark, quote, when)
    return "- %s%s: %s %s (%s)" % (entry.get("id", "?"), mark, " ".join(str(entry.get("ruling", "")).split()),
                                   PARAPHRASE, when)


def unreadable_files(repo, ref, read):
    """How many ruling files the folder lists that read_store did not return: read_store skips a file that is not a
    JSON object, so the folder's names less the entries read is the count."""
    code, listing = ruled_store._git(repo, ["ls-tree", "-z", "--name-only", ref, ruled_store.STORE_DIR])
    names = [n for n in listing.split(b"\0") if n.endswith(b".json")] if code == 0 else []
    return max(len(names) - read, 0)


def rulings_block(slug, step, repo, ref):
    entries, state = ruled_store.read_store(repo, ref)
    if state != "ok":
        return "Rulings: unknown (store %s)" % state
    lines = []
    bad = unreadable_files(repo, ref, len(entries))
    if bad:
        lines.append("Rulings: unknown (%d unreadable ruling file%s)" % (bad, "" if bad == 1 else "s"))
    found = governing(entries, slug, str(step.get("note") or ""))
    lines += [ruling_line(e) for e in found]
    return "\n".join(lines) if lines else "None names this step in the store."


def files_block(step):
    named = []
    for path in PATH.findall(FENCE.sub("", str(step.get("note") or ""))):
        if path not in named:
            named.append(path)
    head = ["Named in the step note: %s" % ", ".join(named)] if named else []
    return "\n".join(head + [FILES_MARKER])


def check_line(step):
    """The Done-check line from the step's optional `done_check` text and `ci_only` flag. The note is never read."""
    given = step.get("done_check")
    line = given.strip() if isinstance(given, str) and given.strip() else CHECK_MARKER
    return line + " (%s)" % PROVED if step.get("ci_only") is True else line


def build(slug, repo=".", ref=ruled_store.STORE_REF, topic=None, cap=DEFAULT_CAP):
    """The brief text for step `slug`. Raises NoStep when the step file cannot be read."""
    step = read_step(slug, repo, ref)
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    text = lambda key: str(step.get(key) or "").strip()  # noqa: E731
    values = {
        "slug": slug, "topic": topic or text("topic") or TOPIC_MARKER, "title": text("title"), "why": text("why"),
        "source": text("source") or "unknown", "files": files_block(step), "rulings": rulings_block(slug, step, repo, ref),
        "check": check_line(step), "cap": str(cap),
    }
    # One pass, so a quote that holds `{{x}}` is never filled again.
    keep = step.get("ci_only") is True  # the batch-CI rule shows only for a step with such a check
    lines = [l for l in template.split("\n") if keep or not l.startswith(CI_ONLY_LINE)]
    template = "\n".join(l[len(CI_ONLY_LINE):] if l.startswith(CI_ONLY_LINE) else l for l in lines)
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def main(argv):
    ap = argparse.ArgumentParser(description="Print a lane brief for one roadmap step.")
    ap.add_argument("slug")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default=ruled_store.STORE_REF)
    ap.add_argument("--topic")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    a = ap.parse_args(argv)
    try:
        out = build(a.slug, a.repo, a.ref, a.topic, a.cap)
    except NoStep as e:
        print("brief_from_step: %s" % e, file=sys.stderr)
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
