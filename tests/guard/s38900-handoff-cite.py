# section 38900
# =========================================================================== handoff-cite
# speak-cite-id-plus-gloss on the session's own handoff. A Write or an Edit of the handoff is judged on the file as
# it reads after the call: the first time an item number appears in it, the number needs its short name beside it.
# The text matrix is ItemCiteTests in lint/test_report_guard.py, on bare_cite. These cases prove the wiring only: the
# check reads the handoff at both places it can sit, an Edit is judged on the whole file, and another path is not.
# None of these configs holds a re-read flag, so handoff-unread never answers first.
FAMILY = "handoff-cite"
HC_SID = "5d2b8c4e-0000-4000-8000-0000000c17e5"   # the main session in these cases
HC_RULE = "speak-cite-id-plus-gloss"              # the rule anchor a refusal names
HC_CLEAN = os.path.join(ROOT, "hc-clean")         # no handoff yet: the empty state
HC_NAMED = os.path.join(ROOT, "hc-named")         # a handoff that names item 46 before any bare cite
HC_BARE = os.path.join(ROOT, "hc-bare")           # a handoff that names no item number
HC_BIG = os.path.join(ROOT, "hc-big")             # a long handoff, with item 46 named on its first line
HC_HOME = os.path.join(ROOT, "hc-home")           # a HOME folder, for the ~/.claude/handoffs spelling
HC_NAMED_TEXT = "# Handoff\n\nOpen: item 46 (search pill clear).\n\n## Next\n\nCheck the page.\n"
HC_BARE_TEXT = "# Handoff\n\nWaiting on the build.\n\n## Next\n\nCheck the page.\n"
HC_BIG_LAST = "Note 1999: nothing to see here."   # the last line of HC_BIG, where an Edit lands
HC_TWICE = os.path.join(ROOT, "hc-twice")         # a handoff whose phrase "(search pill clear)" occurs twice, once after item 46
HC_TWICE_TEXT = "# Handoff\n\nNote (search pill clear).\nOpen: item 46 (search pill clear).\n\n## Next\n\nCheck the page.\n"
HC_BADBYTE = os.path.join(ROOT, "hc-badbyte")     # a handoff with one byte that is not UTF-8
HC_BADBYTE_TEXT = b"# Handoff\n\nWaiting on the STRAY build.\n\n## Next\n\nCheck the page.\n"


HC_TAIL = "".join("\n## %s\n\nx\n" % n for n in (
    "Goal", "Working premises", "Where things stand", "Work in flight", "Next steps", "Files and commands"))


def hc_full(text):
    """`text` with every section the handoff-sections check requires, so only the cite check can refuse it."""
    return text + HC_TAIL


def hc_handoff(config):
    """The session's handoff under `config`, from precompact_handoff, the one home of the path."""
    return hu_paths(config, HC_SID)[0]


def _build_hc_clean():
    os.makedirs(HC_CLEAN, exist_ok=True)


def _build_hc_named():
    write(hc_handoff(HC_NAMED), HC_NAMED_TEXT)


def _build_hc_bare():
    write(hc_handoff(HC_BARE), HC_BARE_TEXT)


def _build_hc_big():
    lines = ["# Handoff", "", "Open: item 46 (search pill clear)."]
    lines += ["Note %d: nothing to see here." % n for n in range(2000)]   # the full-size state
    write(hc_handoff(HC_BIG), "\n".join(lines) + "\n")


def _build_hc_twice():
    write(hc_handoff(HC_TWICE), HC_TWICE_TEXT)


def _build_hc_badbyte():
    # one byte that is not UTF-8, so the handoff cannot be read as text; the edited phrase is still there
    path = hc_handoff(HC_BADBYTE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(HC_BADBYTE_TEXT.replace(b"STRAY", b"\xff"))


lazy_fixture([HC_CLEAN], _build_hc_clean)
lazy_fixture([HC_NAMED], _build_hc_named)
lazy_fixture([HC_BARE], _build_hc_bare)
lazy_fixture([HC_BIG], _build_hc_big)
lazy_fixture([HC_TWICE], _build_hc_twice)
lazy_fixture([HC_BADBYTE], _build_hc_badbyte)


def hc_add(name, expected, config, tool, tool_input, carries=(), **kw):
    """One handoff-cite case: the call runs from NOGIT, as session HC_SID, against `config`. A deny must name
    HC_RULE, so a refusal from another rule cannot pass for this one."""
    rule = HC_RULE if expected == "deny" else None
    add(name, expected, rule, tool=tool, cwd=NOGIT, session=HC_SID, config=config, carries=carries,
        **kw, **tool_input)


# A Write judges the content, which is the file as it reads after the write. The bare number is pinned in the reason.
for _label, _content, _bare in (
        ("a bare item 46", "Open: item 46.\n", "46"),
        ("bare items 46 and 47", "Open: items 46 and 47.\n", "46"),
        ("items 46 (search pill clear) and a bare 47", "Open: items 46 (search pill clear) and 47.\n", "47"),
        ("a bare waiting-page item 46", "Open: waiting-page item 46.\n", "46"),
        ("a bare item 46 first and a named one later", "Open item 46. Later, item 46 (search pill clear).\n", "46")):
    hc_add("handoff-cite: a Write of the handoff with %s is refused" % _label, "deny", HC_CLEAN, "Write",
           {"file_path": hc_handoff(HC_CLEAN), "content": hc_full(_content)}, carries=_bare)
hc_add("handoff-cite: a Write that replaces a handoff naming item 46 with a bare item 46 is refused", "deny", HC_NAMED,
       "Write", {"file_path": hc_handoff(HC_NAMED), "content": hc_full("Open: item 46.\n")}, carries="46")
hc_add("handoff-cite: a Write of the ~/.claude/handoffs spelling of the handoff with a bare item 46 is refused", "deny",
       HC_CLEAN, "Write", {"file_path": os.path.join(HC_HOME, ".claude", "handoffs", HC_SID + ".md"),
                           "content": hc_full("Open: item 46.\n")}, carries="46",
       env={"HOME": HC_HOME, "USERPROFILE": HC_HOME})
for _label, _content in (
        ("a named item 46", "Open: item 46 (search pill clear).\n"),
        ("a named page item 382", "Open: page item 382 (merge-unreviewed-head).\n"),
        ("an item 46 in code", "Use `item 46` as the label.\n")):
    hc_add("handoff-cite: a Write of the handoff with %s is allowed" % _label, "allow", HC_CLEAN, "Write",
           {"file_path": hc_handoff(HC_CLEAN), "content": hc_full(_content)}, silent=True)
hc_add("handoff-cite: a Write of another path with a bare item 46 is not refused by this check", "allow", HC_CLEAN,
       "Write", {"file_path": os.path.join(NOGIT, "notes.md"), "content": hc_full("Open: item 46.\n")}, silent=True)

# An Edit is judged on the file after the edit, so the named cite earlier in the file is what counts.
hc_add("handoff-cite: an Edit that adds a bare item 46 after a named one is allowed", "allow", HC_NAMED, "Edit",
       {"file_path": hc_handoff(HC_NAMED), "old_string": "Check the page.",
        "new_string": "Recheck item 46 after the build."}, silent=True)
hc_add("handoff-cite: an Edit that adds a bare item 46 to a handoff that never names it is refused", "deny", HC_BARE,
       "Edit", {"file_path": hc_handoff(HC_BARE), "old_string": "Check the page.",
                "new_string": "Recheck item 46 after the build."}, carries="46")
hc_add("handoff-cite: an Edit that puts a bare item 46 above the named one is refused", "deny", HC_NAMED, "Edit",
       {"file_path": hc_handoff(HC_NAMED), "old_string": "Open: item 46 (search pill clear).",
        "new_string": "Recheck item 46 first.\nOpen: item 46 (search pill clear)."}, carries="46")
hc_add("handoff-cite: an Edit at the end of a long handoff that adds a named item 47 is allowed", "allow", HC_BIG,
       "Edit", {"file_path": hc_handoff(HC_BIG), "old_string": HC_BIG_LAST,
                "new_string": HC_BIG_LAST + "\nThen item 47 (stale head record) waits."}, silent=True)
hc_add("handoff-cite: an Edit at the end of a long handoff that adds bare items 47 and 48 is refused", "deny", HC_BIG,
       "Edit", {"file_path": hc_handoff(HC_BIG), "old_string": HC_BIG_LAST,
                "new_string": HC_BIG_LAST + "\nThen items 47 and 48 wait."}, carries="47")

# The capital form is read in a Write (the one case red on the old code). A MultiEdit, whose bare cite is only in the
# second edit, and an Edit whose replace_all strips the name from a bare item 46 (the name is on the second of two
# matches, so a single replace would leave it named) are green on the old code; each has a mutant that must flip it.
hc_add("handoff-cite: a Write of the handoff with a capital Item 46 is refused", "deny", HC_CLEAN, "Write",
       {"file_path": hc_handoff(HC_CLEAN), "content": hc_full("Item 46 is open.\n")}, carries="46")
hc_add("handoff-cite: a MultiEdit whose bare item 46 is in its second edit is refused", "deny", HC_BARE, "MultiEdit",
       {"file_path": hc_handoff(HC_BARE), "edits": [
           {"old_string": "Waiting on the build.", "new_string": "Waiting on the build, then the page."},
           {"old_string": "Check the page.", "new_string": "Check item 46 after the build."}]}, carries="46")
hc_add("handoff-cite: an Edit with replace_all that strips the name from a bare item 46 is refused", "deny", HC_TWICE,
       "Edit", {"file_path": hc_handoff(HC_TWICE), "old_string": "(search pill clear)", "new_string": "(name)",
                "replace_all": True}, carries="46")
# Fail open: the handoff holds one byte that is not UTF-8, so the check cannot read it and the call passes.
hc_add("handoff-cite: an Edit of a handoff with an unreadable byte is allowed, since the check cannot read it", "allow",
       HC_BADBYTE, "Edit", {"file_path": hc_handoff(HC_BADBYTE), "old_string": "Check the page.",
                            "new_string": "Check item 46 after the build."}, silent=True)
