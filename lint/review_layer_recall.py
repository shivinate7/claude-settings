#!/usr/bin/env python3
"""Scores each review layer's recall against the incident fixture and prints one JSON report.

  python3 lint/review_layer_recall.py --fixture <fixture.json> [--findings <verdicts.json>]

The report shape is in the docstring of lint/test_review_layer_recall.py. A verdicts file is a
JSON list of {"pr", "layer", "verdict"} rows. A layer's recall is "measured" only when every
incident whose answer key names the layer has a PASS or FAIL row of that layer; a layer with no
incidents, a missing row, or a row whose verdict is anything else reads "unknown", never 0.
A row for one layer never counts for another. A file that is not a list of objects exits 2.
(The flag keeps the name --findings: the test file names it.)
Cost is always "unknown": the review record stores no cost. Reads two local files, no network.
"""
import argparse
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def recall(incidents, rows, layer):
    scope = [i["pr"] for i in incidents if i["layer"] == layer]
    unknown = {"status": "unknown", "caught": None, "of": len(scope)}
    if not scope:
        return unknown
    caught = 0
    for pr in scope:
        marks = [row.get("verdict")
                 for row in rows if row.get("layer") == layer and row.get("pr") == pr]
        if not marks or any(mark not in ("PASS", "FAIL") for mark in marks):
            return unknown
        caught += "FAIL" in marks
    return {"status": "measured", "caught": caught, "of": len(scope)}


def report(fixture, rows):
    incidents = fixture["incidents"]
    return {
        "n": {"incidents": len(incidents), "controls": len(fixture["controls"])},
        "layers": {
            layer: {"recall": recall(incidents, rows, layer), "cost": {"status": "unknown"}}
            for layer in fixture["layers"]
        },
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--findings", dest="verdicts")
    args = parser.parse_args(argv)
    try:
        fixture = load(args.fixture)
        rows = load(args.verdicts) if args.verdicts else []
    except (OSError, ValueError) as exc:
        print("review_layer_recall: cannot read input: %s" % exc, file=sys.stderr)
        return 2
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        print("review_layer_recall: cannot read input: verdicts are not a list of objects", file=sys.stderr)
        return 2
    print(json.dumps(report(fixture, rows), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
