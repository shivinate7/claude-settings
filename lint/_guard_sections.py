"""The one home of how a guard test section file's header reads and what a bad set is.

lint/check_record_slugs.py reads the whole tree with it. hooks/test_guard.py's load_sections runs the files and
reads its header and faults from here too. The folder is not here: hooks/test_guard.py's SECTION_DIR is its one
copy, and lint/rule_audit.py section_dir() reads it. A section file's first line is `# section <n>`, and its
name is `s<n>-<slug>.py`.
"""
import os
import re

HEADER = re.compile(r"# section (\d+)\n")  # matched at the start of the text: the first line only
NAME_NUMBER = re.compile(r"[sS]?(\d+)")  # any leading digits: s43501_x, s43501x, 43501-x and S43501-x each read as 43501


def read(section_dir):
    """[(name, header number or None, text)] of each .py file in section_dir, sorted by name."""
    out = []
    for name in (sorted(os.listdir(section_dir)) if os.path.isdir(section_dir) else []):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(section_dir, name), encoding="utf-8") as f:
            text = f.read()
        head = HEADER.match(text)
        out.append((name, int(head.group(1)) if head else None, text))
    return out


def faults(sections):
    """[(name, message)] for each file of `sections` (from read) that has no header, whose name number is not its
    header number, or that shares its header number with another file."""
    bad = []
    numbers = [n for _, n, _ in sections if n is not None]
    for name, n, _ in sections:
        if n is None:
            bad.append((name, "has no `# section <n>` first line"))
            continue
        m = NAME_NUMBER.match(name)
        if m and int(m.group(1)) != n:
            bad.append((name, "name number %d disagrees with its header, section %d" % (int(m.group(1)), n)))
        if numbers.count(n) > 1:
            bad.append((name, "section number %d is on %d section files" % (n, numbers.count(n))))
    return bad
