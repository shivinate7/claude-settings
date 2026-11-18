#!/usr/bin/env python3
"""Scores each review layer's recall against the incident fixture and prints one JSON report.

  python3 lint/review_layer_recall.py --fixture <fixture.json> [--findings <findings.json>]

The report shape is in the docstring of lint/test_review_layer_recall.py. A layer's recall is
"measured" only when the findings hold a verdict for every incident whose answer key names the
layer; a layer with no incidents, or any incident with no verdict, reads "unknown", never 0.
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
    verdicts = {}
    for row in rows:
        if row.get("layer") == layer:
            verdicts.setdefault(row.get("pr"), set()).add(row.get("verdict"))
    if not scope or any(pr not in verdicts for pr in scope):
        return {"status": "unknown", "caught": None, "of": len(scope)}
    caught = sum(1 for pr in scope if "FAIL" in verdicts[pr])
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
    parser.add_argument("--findings")
    args = parser.parse_args(argv)
    try:
        fixture = load(args.fixture)
        rows = load(args.findings) if args.findings else []
    except (OSError, ValueError) as exc:
        print("review_layer_recall: cannot read input: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(report(fixture, rows), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
