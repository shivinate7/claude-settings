#!/usr/bin/env python3
"""Before a designer spawn, reads its brief. A blind brief must follow the design-explore template and name nothing of today's product. An informed or directed brief must say how many blind lanes its run has.

Decision blind-briefs-use-a-template. Standard library only.

- A blind brief (first line `Lane kind: blind`) follows skills/design-explore/blind-brief.md: a `Lane:`
  line, the free sections Job, Device and Palette, and the fixed sections House rules and Deliver word
  for word. A free section may not name the current product, a screenshot or mockup, a path or link,
  the spec or tokens, or a keep or match rule (brief_faults).
- An informed or directed brief carries `Blind lanes: <n>` with n of 1 or more, or
  `Blind lanes: none, owner: "<the owner's words>"`.
- A designer brief with no kind line is a small change outside design-explore, and passes.

Hook: PreToolUse on Agent and Task. A deny goes through guard_core.refuse(), the one home of the
override pass and the guard.log line, with rule `blind-brief`. Fail open: junk input, a missing
template or an internal error allows the call, with one stderr line for an error. Cost: one python
start per Agent or Task call, no file written but the guard.log line of a deny.

CLI: `python3 blind_brief.py --run DIR [--current NAME ...] [--owner-asked-none WORDS]` checks every
*.md brief in DIR as one explore run (run_faults). `--current` names a view of today's product, refused
as a whole word in a blind brief. Exit 0 clean, 1 with one line per fault, 2 when DIR cannot be read.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
TEMPLATE = os.path.join(HERE, "..", "skills", "design-explore", "blind-brief.md")
RULE = "blind-brief"
SPAWN_TOOLS = ("Agent", "Task")
FREE = ("Job", "Device", "Palette")
FIXED = ("House rules", "Deliver")

KIND_LINE = re.compile(r"^lane kind:\s*(blind|informed|directed)\b", re.I)
LANE_LINE = re.compile(r"^Lane:\s*[A-Za-z0-9][\w-]*-blind-[1-9][0-9]*\s*$")
BLIND_LANES = re.compile(r"^blind lanes:\s*(.*?)\s*$", re.I | re.M)
OWNER_NONE = re.compile(r"^none,\s*owner:\s*\"[^\"]*\w[^\"]*\"$", re.I)
HEADING = re.compile(r"^##\s+(.*?)\s*$")
PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]{2,}>")

_NOUN = (r"(?:products?|apps?|screens?|views?|pages?|layouts?|designs?|ui|look|versions?|sites?|tabs?"
         r"|navigation|nav|clients?)")
# Each class is a list of patterns, matched case-blind against one free section.
PATTERNS = {
    "current": [
        r"\b(?:current|existing|today'?s|present|old|live|shipped)\s+" + _NOUN + r"\b",
        r"\b(?:look\s+at|open|study|inspect|review|see|read|use)\s+(?:the\s+)?(?:web|native|ios|android|live)\s+"
        r"(?:app|site|version|client|screens?|pages?)\b",
        r"\bthe\s+(?:web|native|ios|android)\s+(?:app|client|version)\b",
        r"\bas\s+it\s+(?:is|looks|works|stands)\s+(?:now|today)\b",
        r"\blooks?\s+like\s+(?:the\s+)?(?:current|existing|old|web|today)",
    ],
    "keep": [
        r"\b(?:keep|keeps|kept|keeping|preserve[sd]?|retain[s]?|reuse[sd]?)\s+(?:that|its|this|our|today'?s"
        r"|(?:the\s+)?current|(?:the\s+)?existing)\s+(?:look|feel|style|layout|design|structure|navigation|nav|ui"
        r"|chrome)\b",
        r"\b(?:match|matches|matched|matching|mirror|mirrors|copy|copies)\s+(?:the\s+|that\s+|its\s+|our\s+)?"
        r"(?:current|existing|web|live|old|native|present)\b",
        r"\bsame\s+(?:look|layout|design|structure|views?|screens?|tabs?|navigation)\s+as\b",
        r"\bconsistent\s+with\s+(?:the\s+)?(?:current|existing|web|old|app)\b",
        r"\bstays?\s+(?:close|true)\s+to\b",
    ],
    "screenshot": [
        r"\bscreen\s?shots?\b", r"\bscreen\s?caps?\b", r"\bscreen\s+captures?\b", r"\bmock-?ups?\b",
        r"\bwireframes?\b",
    ],
    "path": [
        r"\bhttps?://", r"\bfile://", r"\blocalhost\b", r"\b127\.0\.0\.1\b",
        r"(?:^|[\s(`'\"])(?:~|\.{1,2})/[\w.-]",
        r"\b(?:docs|src|app|design|captures|screens|public|assets|specs)/[\w.-]+/",
        r"\b[\w-]+\.(?:png|jpe?g|gif|webp|heic|svg|pdf|html?|css|tsx?|jsx?|swift|json|md|txt|figma|sketch)\b",
    ],
    "spec": [
        r"\b(?:the|its|our|design|product|app|ui|screen)\s+spec(?:s|ification)?\b(?!\s+sheets?)",
        r"\bdesign\s+(?:system|doc|docs|records?|decisions?)\b",
        r"\b(?:design|colou?r|style|css|theme)\s+tokens?\b", r"\btokens?\s+(?:file|values?)\b",
        r"(?<![\w-])--[a-z][a-z0-9]*-[\w-]+", r"\bstyle\s*guide\b",
    ],
}
COMPILED = {kind: [re.compile(p, re.I) for p in pats] for kind, pats in PATTERNS.items()}


def kind_of(text):
    """The lane kind of the brief's first `Lane kind:` line, lowercased, or None. The line may come after
    a preamble, so a preamble hides no kind; brief_faults still refuses a blind brief whose first line
    is not the kind."""
    for line in text.splitlines():
        m = KIND_LINE.match(line.strip())
        if m:
            return m.group(1).lower()
    return None


def sections(text):
    """(header lines, {heading: body}, extras, repeated headings). The header is every line before
    the first heading. An extra is (code, text): a heading the template lacks, or a line outside every
    template section."""
    header, parts, extra, repeated, current = [], {}, [], [], None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            name = m.group(1)
            if name in FREE + FIXED:
                if name in parts:
                    repeated.append(name)
                current = name
                parts.setdefault(name, [])
            else:
                extra.append(("section-extra", name))
                current = None
            continue
        if current:
            parts[current].append(line)
        elif not parts and not extra:
            header.append(line)
        elif line.strip():
            extra.append(("outside", line.strip()))
    return header, {k: "\n".join(v).strip() for k, v in parts.items()}, extra, repeated


def flat(text):
    return " ".join(text.split())


def template_fixed(path=None):
    """{heading: body} of the template's fixed sections, or None when the template cannot be read."""
    try:
        with open(path or TEMPLATE, encoding="utf-8") as handle:
            _, parts, _, _ = sections(handle.read())
    except OSError:
        return None
    return {name: parts.get(name, "") for name in FIXED}


def brief_faults(text, current=(), template=None):
    """Faults of one blind brief, as (code, where, matched) triples. An empty list is a clean brief."""
    faults = []
    header, parts, extra, repeated = sections(text)
    lines = [line.strip() for line in header if line.strip()]
    if not lines or not KIND_LINE.match(lines[0]) or kind_of(text) != "blind":
        faults.append(("kind", "first line", lines[0] if lines else ""))
    if not any(LANE_LINE.match(line) for line in lines):
        faults.append(("lane", "header", "no Lane line"))
    for line in lines:
        if not KIND_LINE.match(line) and not LANE_LINE.match(line):
            faults.append(("outside", "header", line))
    for code, name in extra:
        faults.append((code, "body", name))
    for name in repeated:
        faults.append(("section-extra", name, "repeated"))
    for name in FREE + FIXED:
        if name not in parts:
            faults.append(("section-missing", name, ""))
        elif not parts[name]:
            faults.append(("section-empty", name, ""))
    fixed = template_fixed(template)
    if fixed:
        for name in FIXED:
            if name in parts and parts[name] and flat(parts[name]) != flat(fixed[name]):
                faults.append(("fixed-changed", name, ""))
    for line in lines:
        if PLACEHOLDER.search(line):
            faults.append(("placeholder", "header", PLACEHOLDER.search(line).group(0)))
    for name in FREE:
        body = parts.get(name, "")
        hit = PLACEHOLDER.search(body)
        if hit:
            faults.append(("placeholder", name, hit.group(0)))
        for kind, pats in COMPILED.items():
            for pat in pats:
                hit = pat.search(body)
                if hit:
                    faults.append((kind, name, hit.group(0).strip()))
                    break
        for view in current:
            if view and re.search(r"(?<!\w)" + re.escape(view) + r"(?!\w)", body):
                faults.append(("named-view", name, view))
    return faults


def blind_lanes_ok(text):
    """True when an informed or directed brief says its run has a blind lane, or carries the owner's
    words for none."""
    m = BLIND_LANES.search(text)
    if not m:
        return False
    value = m.group(1)
    if value.isdigit():
        return int(value) >= 1
    return bool(OWNER_NONE.match(value))


def run_faults(texts, owner_none="", current=(), template=None):
    """Faults of one explore run, as (code, where, matched) triples. `where` is the brief's index."""
    faults, blind = [], 0
    for index, text in enumerate(texts):
        kind = kind_of(text)
        if kind is None:
            faults.append(("kind", "brief %d" % (index + 1), "no Lane kind line"))
        elif kind == "blind":
            blind += 1
            faults.extend((code, "brief %d, %s" % (index + 1, where), matched)
                          for code, where, matched in brief_faults(text, current, template))
    if not texts:
        faults.append(("no-brief", "run", ""))
    elif blind == 0 and not owner_none.strip():
        faults.append(("no-blind-lane", "run", "no blind lane, and no owner words for none"))
    return faults


def describe(faults):
    return "; ".join("%s (%s%s)" % (code, where, ": " + matched[:60] if matched else "")
                     for code, where, matched in faults)


DENY_BLIND = ("this blind designer brief breaks the template: %s. Build it again from the "
              "design-explore blind template: the job in the users' words, the device, the palette, and "
              "the fixed House rules and Deliver text. Name nothing of today's product.")
DENY_COUNT = ("an informed or directed designer brief must carry a line `Blind lanes: <n>`, with n of 1 or "
              "more, or `Blind lanes: none, owner: \"<the owner's words>\"`. Start the run's blind lanes "
              "too (skill design-explore).")


def deny(payload, tool, reason, matched):
    """Deny through guard_core.refuse(), which lets an owner override pass lift it. refuse() exits."""
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_pass_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_pass_veto(lambda: False)
        guard_core.refuse(tool, "deny", RULE, reason, matched)
    except SystemExit:
        raise
    except Exception:  # no guard_core: no pass can be read, so the deny stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": RULE + ": " + reason}}))
    sys.exit(0)


def hook(stdin):
    try:
        payload = json.loads(stdin)
    except ValueError:
        return
    if not isinstance(payload, dict) or payload.get("tool_name") not in SPAWN_TOOLS:
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    role, prompt = tool_input.get("subagent_type"), tool_input.get("prompt")
    if not isinstance(role, str) or not isinstance(prompt, str):
        return
    if role.rsplit(":", 1)[-1].strip().lower() != "designer":
        return
    kind = kind_of(prompt)
    if kind == "blind":
        if template_fixed() is None:
            print("blind_brief: template unreadable, fixed sections not checked", file=sys.stderr)
        faults = brief_faults(prompt)
        if faults:
            deny(payload, payload["tool_name"], DENY_BLIND % ", ".join(dict.fromkeys(f[0] for f in faults)),
                 describe(faults)[:200])
    elif kind in ("informed", "directed") and not blind_lanes_ok(prompt):
        deny(payload, payload["tool_name"], DENY_COUNT, "Blind lanes line: " + kind)


def cli(argv):
    parser = argparse.ArgumentParser(description="Check the briefs of one design-explore run.")
    parser.add_argument("--run", required=True, help="the folder of the run's *.md briefs")
    parser.add_argument("--current", action="append", default=[], help="a view of today's product")
    parser.add_argument("--owner-asked-none", default="", help="the owner's words for a run with no blind lane")
    args = parser.parse_args(argv)
    try:
        names = sorted(n for n in os.listdir(args.run) if n.endswith(".md"))
        texts = []
        for name in names:
            with open(os.path.join(args.run, name), encoding="utf-8") as handle:
                texts.append(handle.read())
    except OSError as exc:
        print("blind_brief: cannot read %s: %s" % (args.run, exc), file=sys.stderr)
        return 2
    faults = run_faults(texts, args.owner_asked_none, args.current)
    for code, where, matched in faults:
        where = re.sub(r"^brief (\d+)", lambda m: names[int(m.group(1)) - 1], where)
        print("%s: %s%s" % (code, where, ": " + matched if matched else ""))
    print("blind_brief: %d brief(s), %d fault(s)" % (len(texts), len(faults)))
    return 1 if faults else 0


def main():
    if len(sys.argv) > 1:
        return cli(sys.argv[1:])
    try:
        hook(sys.stdin.read())
    except SystemExit:
        raise
    except Exception as exc:  # fail open; one stderr line shows in --debug
        print("blind_brief: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
