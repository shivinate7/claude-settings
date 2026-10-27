#!/usr/bin/env python3
"""Gives each repo one colour, from one registry (docs/design/repo-colours.json).

    python3 lint/repo_colour.py <repo> [--registry PATH]

Prints one hex, such as #3d5af1. A repo the registry names gets its colour. Any other repo gets a
hue drawn from its name: FNV-1a over the name gives a start hue, and the draw steps round the wheel
until the hue keeps the rule's gap from each state hue and from each other repo's hue. A grey
registry colour takes no hue. If no hue keeps every gap, the draw takes the widest gap left. The
same name and registry always give the same colour. `owner/name` reads as `name`.

The waiting page and any repo's design work call `colour_for`; none keeps a copy of the rule.
Exits 0 with the hex. Exits 2 with no repo, or when the registry cannot be read: the colour is
unknown, never a guess.
Cost: one read of the registry per call. No process, file or log.
"""
import colorsys
import json
import re
import os
import sys

REGISTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "design", "repo-colours.json")


def load(registry=REGISTRY):
    with open(registry, encoding="utf-8") as f:
        return json.load(f)


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def hue_of(hex6, min_saturation=0.2):
    """The colour's HSL hue in degrees, or None for a grey."""
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    return None if s < min_saturation else h * 360


def name_hue(name):
    # FNV-1a, 32 bits, over UTF-16 code units: the same start hue as the waiting-page mockup's draw.
    x = 2166136261
    units = name.encode("utf-16-le")
    for i in range(0, len(units), 2):
        x ^= units[i] | units[i + 1] << 8
        x = (x * 16777619) & 0xFFFFFFFF
    return x % 360


def draw_hue(start, taken, rule):
    blocks = [(s, rule["state_gap"]) for s in rule["state_hues"]] + [(t, rule["repo_gap"]) for t in taken]
    h, best, best_gap = start, start, -1
    for _ in range(360):
        if all(hue_gap(h, b) >= gap for b, gap in blocks):
            return h
        widest = min((hue_gap(h, b) for b, _ in blocks), default=360)
        if widest > best_gap:
            best, best_gap = h, widest
        h = (h + rule["step"]) % 360
    return best


def colour_for(repo, registry=REGISTRY):
    data = load(registry)
    rule, repos = data["rule"], data["repos"]
    name = repo.rstrip("/").rsplit("/", 1)[-1]
    if name in repos:
        hex6 = repos[name]
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex6):
            raise ValueError("%s is not #rrggbb: %r" % (name, hex6))
        return hex6.lower()
    taken = [h for h in (hue_of(c, rule["min_saturation"]) for c in repos.values()) if h is not None]
    h = draw_hue(name_hue(name), taken, rule)
    r, g, b = colorsys.hls_to_rgb(h / 360, rule["lightness"] / 100, rule["saturation"] / 100)
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in (r, g, b))


def main(argv):
    args = argv[1:]
    registry = REGISTRY
    if "--registry" in args:
        i = args.index("--registry")
        if i + 1 >= len(args):
            print("repo_colour: --registry needs a path", file=sys.stderr)
            return 2
        registry = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: repo_colour.py <repo> [--registry PATH]", file=sys.stderr)
        return 2
    try:
        print(colour_for(args[0], registry))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("repo_colour: registry unreadable, colour unknown: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
