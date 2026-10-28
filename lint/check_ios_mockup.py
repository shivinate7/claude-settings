#!/usr/bin/env python3
"""Checks one iPhone mockup page for the parts a check can hold (roadmap step c192, skill ios-apps, Mockups).

A designer lane on an iPhone app draws with the system font, respects the safe-area insets, and draws the
iPhone Duo folded first, then unfolded, each pose in its own frame. The taste verdict (native or web-like)
stays with the design reviewer. Standard library only.

    python3 lint/check_ios_mockup.py <mockup.html> [<mockup.html> ...]

Faults, one of each code at most per page:
- system-font: no CSS font-family whose first family is -apple-system or system-ui.
- safe-area: no CSS env(safe-area-inset-...) call.
- duo-frames: no element with data-device="iphone-duo-folded" and one with data-device="iphone-duo-unfolded",
  folded first in document order.

CSS is the text of <style> elements and of style="" attributes, never script text. CSS comments are
stripped with strings respected, so a comment opener inside a CSS string is not a comment. An HTML comment
holds no frame.

Prints one `<file>: <code>: <detail>` line per fault. Exits 0 when clean, 1 with faults, and 2 when a file
cannot be read. It is not a CI gate over a repo's design folder: the designer and skills design-explore and
ios-apps run it on a new mockup. Cost: one python start per run; it writes no file.
"""
import html.parser
import re
import sys

FOLDED, UNFOLDED = "iphone-duo-folded", "iphone-duo-unfolded"  # device ids in lint/layout.json
SYSTEM_FONTS = ("-apple-system", "system-ui")
FONT_FAMILY = re.compile(r"(?<![\w-])font-family\s*:\s*([^;{}]*)", re.I)
FONT_SHORTHAND = re.compile(r"(?<![\w-])font\s*:\s*([^;{}]*)", re.I)
SAFE_AREA = re.compile(r"(?<![\w-])env\(\s*safe-area-inset-(?:top|right|bottom|left)\b", re.I)


def strip_css_comments(css):
    """`css` with each /* ... */ comment replaced by a space. A quoted string is kept whole, so "/*" inside
    it opens no comment. A string ends at its closing quote or at an unescaped newline, so a lone quote
    cannot swallow the rest of the sheet."""
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c == "/" and css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c and css[j] != "\n":
                j += 2 if css[j] == "\\" else 1
            out.append(css[i:j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


class _Page(html.parser.HTMLParser):
    """Collects the CSS of a page and the data-device values of its elements, in document order. The
    parser hands <style> and <script> text over raw, and drops HTML comments."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.css, self.frames, self._in = [], [], None

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "style" and value:
                self.css.append(value)
            elif name == "data-device" and value:
                self.frames.append(value.strip())
        if tag in ("style", "script"):
            self._in = tag

    def handle_endtag(self, tag):
        if tag == self._in:
            self._in = None

    def handle_data(self, data):
        if self._in == "style":
            self.css.append(data)


def _first_family(value):
    value = value.strip()
    if value.startswith(("'", '"')):
        return value[1:].split(value[0], 1)[0].strip().lower()
    return value.split(",", 1)[0].strip().lower()


def _shorthand_family(value):
    """The first family of a `font:` shorthand: the text after the size, as in `16px/1.4 -apple-system`."""
    m = re.search(r"\d(?:[\w.%]*)(?:\s*/\s*[\w.%]+)?\s+(.+)$", value.strip())
    return _first_family(m.group(1)) if m else ""


def faults(text):
    """[(code, detail)] for one mockup page. An empty list is a clean page."""
    page = _Page()
    page.feed(text)
    page.close()
    css = strip_css_comments("\n".join(page.css))
    found = []
    families = [_first_family(v) for v in FONT_FAMILY.findall(css)]
    families += [_shorthand_family(v) for v in FONT_SHORTHAND.findall(css)]
    if not any(f in SYSTEM_FONTS for f in families):
        found.append(("system-font", "no font-family starts with -apple-system or system-ui"))
    if not SAFE_AREA.search(css):
        found.append(("safe-area", "no env(safe-area-inset-...) in the CSS"))
    frames = page.frames
    if FOLDED not in frames or UNFOLDED not in frames:
        missing = [f for f in (FOLDED, UNFOLDED) if f not in frames]
        found.append(("duo-frames", "no element with data-device=" + " or ".join('"%s"' % f for f in missing)))
    elif frames.index(UNFOLDED) < frames.index(FOLDED):
        found.append(("duo-frames", 'the "%s" frame comes before the "%s" frame' % (UNFOLDED, FOLDED)))
    return found


def main(argv):
    if not argv:
        print("check_ios_mockup: usage: check_ios_mockup.py <mockup.html> [...]", file=sys.stderr)
        return 2
    status = 0
    for path in argv:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as err:
            print("check_ios_mockup: cannot read %s: %s" % (path, err), file=sys.stderr)
            return 2
        for code, detail in faults(text):
            print("%s: %s: %s" % (path, code, detail))
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
