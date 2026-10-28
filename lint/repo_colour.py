#!/usr/bin/env python3
"""Gives each repo one colour, from one registry (docs/design/repo-colours.json).

    python3 lint/repo_colour.py <repo> [--registry PATH] [--root PATH]
    python3 lint/repo_colour.py identity <root> [--registry PATH]
    python3 lint/repo_colour.py drift <root>... [--registry PATH]

Prints one hex, such as #3d5af1. With --root, the checkout's own extras colour
(layout.waiting_page_colour) wins; an invalid one is unknown. A repo the registry names gets its colour. Any other repo gets a
hue drawn from its name: FNV-1a over the name gives a start hue, and the draw steps round the wheel
until the hue keeps the rule's gap from each state hue and from each other repo's hue. A grey
registry colour takes no hue. If no hue keeps every gap, the draw takes the widest gap left. The
same name and registry always give the same colour. `owner/name` reads as `name`.

The waiting page and any repo's design work call `colour_for`; none keeps a copy of the rule.
Exits 0 with the hex. Exits 2 with no repo, or when the registry or the extras colour cannot be
read: the colour is unknown, never a guess.

identity prints the waiting page identity of the checkout at <root> as JSON, {"brand", "icon"} (skill
waiting-page): brand is the colour above, and icon is the extras icon file as a data: URI. The icon is
left out, with a line on stderr, when the file is missing, is not .svg or .png, or its URI passes the
page's ICON_MAX, read from page.html so the two never differ. The repo's name is its GitHub origin's,
else the folder's.

drift reads, for each checkout, its extras colour and its own accent source (the registry's "accents":
{file, token}; a .json file's token is a dotted key, any other file's a CSS custom property, first
declaration), and prints one line per checkout. Exits 0 when each value matches the registry, 1 when
any differs (drift wins over unknown), 2 when any cannot be read or the repo is not in the registry:
unknown, never clear. Other repos are not in CI, so it runs on demand only.
Cost: per call, one read of the registry; identity adds the extras file, the git config and the icon;
drift adds the extras file, the git config and one source file per checkout. No process starts and no
file or log is written (test Drift.test_cost_reads_only_no_process_no_write).
"""
import base64
import colorsys
import json
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layout  # noqa: E402  the one home of the extras keys (lint/layout.py)

ROOT = os.path.dirname(HERE)
REGISTRY = os.path.join(ROOT, "docs", "design", "repo-colours.json")
PAGE = os.path.join(ROOT, "skills", "waiting-page", "page.html")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
ICON_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


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


def colour_for(repo, registry=REGISTRY, root=None):
    """The repo's colour: the extras colour of the checkout at `root` when set, else the registry's,
    else the draw. layout.LayoutError when the extras colour is set but not #rrggbb."""
    own = layout.waiting_page_colour(root) if root is not None else None
    if own:
        return own
    data = load(registry)
    rule, repos = data["rule"], data["repos"]
    name = repo.rstrip("/").rsplit("/", 1)[-1]
    if name in repos:
        hex6 = repos[name]
        if not HEX.fullmatch(hex6):
            raise ValueError("%s is not #rrggbb: %r" % (name, hex6))
        return hex6.lower()
    taken = [h for h in (hue_of(c, rule["min_saturation"]) for c in repos.values()) if h is not None]
    h = draw_hue(name_hue(name), taken, rule)
    r, g, b = colorsys.hls_to_rgb(h / 360, rule["lightness"] / 100, rule["saturation"] / 100)
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in (r, g, b))


def name_of(root):
    """The repo name of the checkout at `root`: its GitHub origin's, else its folder's."""
    found = layout.repo_name(root)
    return found.rsplit("/", 1)[-1] if found else os.path.basename(os.path.abspath(root))


def icon_max(page=None):
    """The page's ICON_MAX, the longest icon data URI it shows."""
    page = page or PAGE
    with open(page, encoding="utf-8") as f:
        hit = re.search(r"\bICON_MAX = (\d+)", f.read())
    if not hit:
        raise ValueError("%s holds no ICON_MAX" % page)
    return int(hit.group(1))


def icon_uri(root):
    """(data URI, None) for the extras icon of `root`, or (None, why) when it is left out; (None, None)
    when the repo names none."""
    try:
        rel = layout.waiting_page_icon(root)
    except layout.LayoutError as e:
        return None, str(e)
    if rel is None:
        return None, None
    kind = ICON_TYPES.get(os.path.splitext(rel)[1].lower())
    if kind is None:
        return None, "%s is not .svg or .png" % rel
    try:
        with open(os.path.join(root, *rel.split("/")), "rb") as f:
            data = f.read()
    except OSError as e:
        return None, "%s cannot be read: %s" % (rel, e)
    if kind == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, "%s is not a PNG" % rel
    try:
        most = icon_max()
    except (OSError, ValueError) as e:
        return None, "the page's ICON_MAX cannot be read: %s" % e
    uri = "data:%s;base64,%s" % (kind, base64.b64encode(data).decode("ascii"))
    if len(uri) > most:
        return None, "%s is %d characters as a data URI, over the page's ICON_MAX %d" % (rel, len(uri), most)
    return uri, None


def identity(root, registry=REGISTRY):
    """{brand, icon} for the waiting page of the checkout at `root`, and the reason any icon was left out."""
    found = {"brand": colour_for(name_of(root), registry, root)}
    uri, why = icon_uri(root)
    if uri:
        found["icon"] = uri
    return found, why


def _hex(value):
    v = value.strip() if isinstance(value, str) else ""
    if re.fullmatch(r"#[0-9a-fA-F]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    if not HEX.fullmatch(v):
        raise ValueError("%r is not a hex colour" % value)
    return v.lower()


def _uncommented(text):
    """`text` with /* */, // and <!-- --> comments blanked, in one pass that skips string literals.
    A ' or " string ends at its line's end, so a lone quote in text (<p>Don't</p>) hides no comment
    on later lines; a ` template literal may span lines. A // right after ":" is a URL, not a comment."""
    out, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if c == quote or (c == "\n" and quote != "`"):
                quote = None
            out.append(c)
            i += 1
            continue
        for opener, closer in (("/*", "*/"), ("<!--", "-->"), ("//", "\n")):
            if text.startswith(opener, i) and not (opener == "//" and i and text[i - 1] == ":"):
                end = text.find(closer, i + len(opener))
                i = n if end < 0 else end + (0 if closer == "\n" else len(closer))
                out.append(" ")
                break
        else:
            if c in "\"'`":
                quote = c
            out.append(c)
            i += 1
    return "".join(out)


def accent(root, source):
    """The hex at the registry's accent `source` ({file, token}) in the checkout at `root`."""
    path = os.path.join(root, *layout._safe(source["file"], "accents").split("/"))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        value = json.loads(text)
        for key in source["token"].split("."):
            value = value[key]
        return _hex(value)
    hit = re.search(r"(?<![\w-])%s\s*:\s*([^;}\n]*)" % re.escape(source["token"]), _uncommented(text))
    if not hit:
        raise ValueError("%s declares no %s" % (source["file"], source["token"]))
    return _hex(hit.group(1))


def drift_line(root, data):
    """(status, line) for one checkout: status 0 clean, 1 drift, 2 unknown."""
    name = name_of(root)
    want = data["repos"].get(name)
    if want is None:
        return 2, "%s: unknown: not in the registry" % name
    want, found = want.lower(), []
    try:
        own = layout.waiting_page_colour(root)
        if own:
            found.append((layout.WAITING_PAGE_COLOUR, own))
        source = data.get("accents", {}).get(name)
        if source:
            found.append(("%s %s" % (source["file"], source["token"]), accent(root, source)))
    except (OSError, ValueError, KeyError, TypeError, layout.LayoutError) as e:
        return 2, "%s: unknown: %s" % (name, e)
    off = ["%s is %s" % (where, v) for where, v in found if v != want]
    if off:
        return 1, "%s: drift: %s; the registry has %s" % (name, ", ".join(off), want)
    return 0, "%s: clean (%s)" % (name, ", ".join(w for w, _ in found) or "no source of its own")


def drift(roots, registry=REGISTRY):
    """[(status, line)] for each checkout in `roots`."""
    data = load(registry)
    return [drift_line(root, data) for root in roots]


def _flag(args, flag):
    """Pops `flag PATH` from `args`: (value or None, ok)."""
    if flag not in args:
        return None, True
    i = args.index(flag)
    if i + 1 >= len(args):
        return None, False
    value = args[i + 1]
    del args[i:i + 2]
    return value, True


USAGE = "usage: repo_colour.py <repo> [--registry PATH] [--root PATH] | identity <root> | drift <root>..."


def main(argv):
    args = argv[1:]
    registry, ok = _flag(args, "--registry")
    root, ok2 = _flag(args, "--root")
    if not (ok and ok2):
        print("repo_colour: --registry and --root need a path", file=sys.stderr)
        return 2
    registry = registry or REGISTRY
    verb = args[0] if args else None
    if verb == "drift" and len(args) > 1 and root is None:
        try:
            results = drift(args[1:], registry)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            print("repo_colour: registry unreadable, drift unknown: %s" % e, file=sys.stderr)
            return 2
        for _, line in results:
            print(line)
        codes = {code for code, _ in results}
        return 1 if 1 in codes else 2 if 2 in codes else 0
    if verb == "identity" and len(args) == 2 and root is None:
        try:
            found, why = identity(args[1], registry)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, layout.LayoutError) as e:
            print("repo_colour: identity unknown: %s" % e, file=sys.stderr)
            return 2
        if why:
            print("repo_colour: icon left out: %s" % why, file=sys.stderr)
        print(json.dumps(found))
        return 0
    if len(args) != 1 or verb in ("drift", "identity"):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        print(colour_for(args[0], registry, root))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("repo_colour: registry unreadable, colour unknown: %s" % e, file=sys.stderr)
        return 2
    except layout.LayoutError as e:
        print("repo_colour: extras colour unreadable, colour unknown: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
