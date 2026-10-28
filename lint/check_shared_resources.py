#!/usr/bin/env python3
"""Checks the "shared-resources" declaration in a repo's extras file (decision shared-resource-owner).

A shared machine names one owning repo, its preflight and its hold record. lint/layout.py
`shared_resources()` is the one reader and holds the rules: owner and preflight are present, paths
stay inside the owner repo, and the owner repo holds its preflight file.

    python3 lint/check_shared_resources.py [--root DIR]

Exits 0 and prints nothing when clean. Exits 1 and prints each problem as
`check_shared_resources: FAIL: ...`. A source it cannot read is red, never green.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def problems(root):
    spec = importlib.util.spec_from_file_location("layout_under_check", os.path.join(HERE, "layout.py"))
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    try:
        layout.shared_resources(root)
    except layout.LayoutError as err:
        return [str(err)]
    return []


def main(argv):
    root = os.path.dirname(HERE)
    if argv[:1] == ["--root"] and len(argv) == 2:
        root = os.path.abspath(argv[1])
    elif argv:
        print("check_shared_resources: FAIL: usage: check_shared_resources.py [--root DIR]")
        return 1
    try:
        found = problems(root)
    except Exception as err:  # a check that cannot read its sources is red, never green
        print("check_shared_resources: FAIL: cannot read the layout or extras file: %s: %s" % (type(err).__name__, err))
        return 1
    for line in found:
        print("check_shared_resources: FAIL: " + line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
