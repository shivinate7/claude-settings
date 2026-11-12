# section 38287
FAMILY = "handoff-sections"
FAMILIES["handoff-sections"] = "a write that leaves a session's handoff without a section the prompt's marker names is refused, naming the sections; the marker is the one list; the fail-open copies; and the cost"
HS_RULE = "handoff-sections"
# The refusal names the missing sections and may name the handoff it judges: under the config folder.
REASON_MAY_NAME["handoff-sections"] = (ROOT, slash(ROOT), ".claude")
HS_SID = "5d2a7c10-0000-4000-8000-00000000f00d"      # the session that writes
HS_OTHER = "9e41b0c3-0000-4000-8000-00000000beef"    # another session's handoff
HS_SECTIONS = ("Goal", "Working premises", "Where things stand", "Work in flight", "Next steps",
               "Files and commands")
HS_TAIL = ("Work in flight", "Next steps", "Files and commands")   # the three a cut tail loses
HS_BODIES = {
    "Goal": "Ship the handoff section check (owner message, 2026-11-08).\n",
    "Working premises": "- P1 [ruling] Six sections are required. Source: owner, 2026-11-08. Checked 2026-11-08.\n",
    "Where things stand": "Branch hsk-tests at 2ac382cc6. No pull request.\n",
    "Work in flight": "Nothing in flight.\n",
    "Next steps": "The builder adds the check.\n",
    "Files and commands": "hooks/guard.py and hooks/precompact_handoff.py.\n",
}
HS_MARKER = re.compile(r"<!--\s*handoff-sections:\s*(.*?)\s*-->")
HS_GAP = "3c6e9a41-0000-4000-8000-00000000d1ce"    # a session whose handoff already lacks Next steps
HS_CFG = os.path.join(ROOT, "hs-cfg")              # the installed prompt, as the repo holds it
HS_CFG_NOMARK = os.path.join(ROOT, "hs-nomark")    # the installed prompt with its marker line removed
HS_CFG_DIR = os.path.join(ROOT, "hs-dir")          # the prompt path is a directory
HS_CFG_BYTES = os.path.join(ROOT, "hs-bytes")      # the prompt is not UTF-8
HS_CFG_EXTRA = os.path.join(ROOT, "hs-extra")      # the marker names one section more
HS_CFG_LESS = os.path.join(ROOT, "hs-less")        # the marker drops Files and commands
HS_CFG_PUNCT = os.path.join(ROOT, "hs-punct")      # the marker names Goal) and Next steps., with their punctuation
HS_PUNCT_NAMES = {"Goal": "Goal)", "Next steps": "Next steps."}   # a section's name in the marker and its heading
HS_PROMPT = os.path.join(HERE, "precompact_handoff_prompt.md")
HS_OPEN = "Open questions"                         # the section HS_CFG_EXTRA's marker adds


def hs_text(omit=(), premises=None):
    """A handoff holding every section but those in `omit`, each under its own `## ` heading. `premises`, when
    given, is the Working premises body: one line per premise, in order."""
    parts = ["# Handoff\n\n"]
    for name in HS_SECTIONS:
        if name not in omit:
            body = HS_BODIES[name]
            if name == "Working premises" and premises is not None:
                body = "".join(line + "\n" for line in premises)
            parts.append("## %s\n%s\n" % (name, body))
    return "".join(parts)


HS_FULL = hs_text()
HS_LAST = HS_FULL[HS_FULL.index("## Work in flight\n"):]   # the cut tail: three sections, to the end


def hs_prompt_text():
    with open(HS_PROMPT, "r", encoding="utf-8") as f:
        return f.read()


def hs_marker_names(text):
    """The names on the marker line of `text`, in order; the six sections when it has none."""
    m = HS_MARKER.search(text)
    return [n.strip() for n in m.group(1).split("|")] if m else list(HS_SECTIONS)


def hs_prompt_with(text, names):
    """`text` with its marker line set to `names`, appended when it has none."""
    line = "<!-- handoff-sections: %s -->" % " | ".join(names)
    if HS_MARKER.search(text):
        return HS_MARKER.sub(lambda _m: line, text, count=1)
    return text + "\n" + line + "\n"


def hs_prompt_path(config):
    with hu_config(config):
        return ph.prompt_path()


def hs_handoff(config, session=HS_SID):
    with hu_config(config):
        return ph.handoff_path(session)


def hs_install(config, text):
    write(hs_prompt_path(config), text)


def hs_write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def _build_hs_intact():
    hs_install(HS_CFG, hs_prompt_text())
    write(hs_handoff(HS_CFG), HS_FULL)   # the Edit and MultiEdit cases edit this file on disk
    write(hs_handoff(HS_CFG, HS_GAP), hs_text(omit=("Next steps",)))   # a handoff that already lacks Next steps


def _build_hs_nomark():
    hs_install(HS_CFG_NOMARK, HS_MARKER.sub("", hs_prompt_text()))


def _build_hs_dir():
    os.makedirs(hs_prompt_path(HS_CFG_DIR), exist_ok=True)


def _build_hs_bytes():
    hs_write_bytes(hs_prompt_path(HS_CFG_BYTES), b"\xff\xfe" + hs_prompt_text().encode("utf-8"))


def _build_hs_extra():
    text = hs_prompt_text()
    hs_install(HS_CFG_EXTRA, hs_prompt_with(text, hs_marker_names(text) + [HS_OPEN]))


def _build_hs_less():
    text = hs_prompt_text()
    hs_install(HS_CFG_LESS, hs_prompt_with(text, [n for n in hs_marker_names(text)
                                                  if n != "Files and commands"]))


def hs_punct_text(omit=()):
    """A handoff holding every section but those in `omit`, each heading the marker's name verbatim: Goal) and
    Next steps. keep their punctuation."""
    parts = ["# Handoff\n\n"]
    for name in HS_SECTIONS:
        if name not in omit:
            parts.append("## %s\n%s\n" % (HS_PUNCT_NAMES.get(name, name), HS_BODIES[name]))
    return "".join(parts)


def _build_hs_punct():
    text = hs_prompt_text()
    hs_install(HS_CFG_PUNCT, hs_prompt_with(text, [HS_PUNCT_NAMES.get(n, n) for n in HS_SECTIONS]))


lazy_fixture([HS_CFG], _build_hs_intact)
lazy_fixture([HS_CFG_NOMARK], _build_hs_nomark)
lazy_fixture([HS_CFG_DIR], _build_hs_dir)
lazy_fixture([HS_CFG_BYTES], _build_hs_bytes)
lazy_fixture([HS_CFG_EXTRA], _build_hs_extra)
lazy_fixture([HS_CFG_LESS], _build_hs_less)
lazy_fixture([HS_CFG_PUNCT], _build_hs_punct)
HS_HANDOFF = hs_handoff(HS_CFG)

# A refusal names every missing section, and names no section that is present. The reason may name the
# handoff it judges, which sits under the config folder (REASON_MAY_NAME).
add("handoff-sections: a Write that drops Work in flight, Next steps and Files and commands is refused, naming the three",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_TAIL, lacks=("Goal", "Working premises", "Where things stand"),
    file_path=HS_HANDOFF, content=hs_text(omit=HS_TAIL))
add("handoff-sections: a Write that keeps all six sections passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF, content=hs_text())
add("handoff-sections: a full-size handoff that keeps all six sections passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF,
    content=HS_FULL.replace(HS_BODIES["Where things stand"],
                            "Branch hsk-tests at 2ac382cc6.\n" + "A line of state, kept.\n" * 6000))
add("handoff-sections: a Write that empties the handoff is refused, naming all six sections",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_SECTIONS, file_path=HS_HANDOFF, content="")
HS_HEADINGS = (
    "# goal\n\n## WORKING PREMISES\n- P1 [read] The file says so. Source: hooks/guard.py:1. Checked 2026-11-08.\n\n"
    "## Where things stand (as of 15:26)\nBranch hsk-tests.\n\n"
    "## Work in flight:\nNothing in flight.\n\n## Next steps\nThe builder adds the check.\n\n"
    "## Files and commands that matter\nhooks/guard.py\n")
add("handoff-sections: headings match on the name, in any case, with text after the name, and pass",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF, content=HS_HEADINGS)
HS_WRONG_LEVEL = (
    "# Handoff\n\n## Goal\nShip it.\n\n## Working premises\n- P1 [assumed] A guess. Source: none. Checked never.\n\n"
    "## Where things stand\nBranch.\n\n## Work in flight\nNothing.\n\n### Next steps\nGo on.\n\n"
    "Next steps are below.\n\n## Files and commands\nhooks/guard.py\n")
add("handoff-sections: Next steps at ### level, or named only in a sentence, is no heading and is refused",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=("Next steps",), lacks=("Goal", "Working premises", "Where things stand", "Work in flight",
                                    "Files and commands"),
    file_path=HS_HANDOFF, content=HS_WRONG_LEVEL)
add("handoff-sections: another session's handoff is refused the same way, naming the three",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_TAIL, lacks=("Goal", "Working premises", "Where things stand"),
    file_path=hs_handoff(HS_CFG, HS_OTHER), content=hs_text(omit=HS_TAIL))
add("handoff-sections: a repo's own HANDOFF.md is not a session handoff, and passes",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=os.path.join(NOGIT, "HANDOFF.md"), content=hs_text(omit=HS_TAIL))
add("handoff-sections: a file named handoff.md outside the config folder is not a session handoff, and passes",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=os.path.join(NOGIT, "notes", "handoff.md"), content=hs_text(omit=HS_TAIL))
add("handoff-sections: an Edit that cuts the tail after Where things stand is refused, naming the three",
    "deny", HS_RULE, tool="Edit", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_TAIL, lacks=("Goal", "Working premises", "Where things stand"),
    file_path=HS_HANDOFF, old_string=HS_LAST, new_string="")
add("handoff-sections: an Edit that keeps all six sections passes, silently",
    "allow", tool="Edit", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF, old_string="Nothing in flight.\n",
    new_string="Nothing in flight; the red run is recorded.\n")
add("handoff-sections: a MultiEdit whose second edit cuts the tail is refused, naming the three",
    "deny", HS_RULE, tool="MultiEdit", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_TAIL, lacks=("Goal", "Working premises", "Where things stand"),
    file_path=HS_HANDOFF,
    edits=[{"old_string": "Branch hsk-tests at", "new_string": "Branch hsk-tests2 at"},
           {"old_string": HS_LAST, "new_string": ""}])
add("handoff-sections: a MultiEdit that keeps all six sections passes, silently",
    "allow", tool="MultiEdit", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF,
    edits=[{"old_string": "The builder adds the check.", "new_string": "The builder adds the check, then the red run."},
           {"old_string": "Nothing in flight.\n", "new_string": "Nothing in flight; the red run is recorded.\n"}])

# The marker is the one list. A name it adds is required; a name it drops is not, and the control shows
# the same write is refused while the marker still names that section.
add("handoff-sections: a name the marker adds is required: a Write without it is refused, naming it",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG_EXTRA,
    carries=(HS_OPEN,), lacks=HS_SECTIONS,
    file_path=hs_handoff(HS_CFG_EXTRA), content=hs_text())
add("handoff-sections: a name the marker drops is not required: a Write without it passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG_LESS, silent=True,
    file_path=hs_handoff(HS_CFG_LESS), content=hs_text(omit=("Files and commands",)))
add("handoff-sections: with the same marker, a Write without Next steps is still refused",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG_LESS,
    carries=("Next steps",), lacks=("Goal", "Working premises", "Where things stand", "Work in flight",
                                    "Files and commands"),
    file_path=hs_handoff(HS_CFG_LESS), content=hs_text(omit=("Next steps",)))


# A handoff that already lacks a section drops nothing when an edit leaves it that way, so an edit to its Goal
# passes. Only a write that removes a section the handoff holds is refused. HS_GAP's handoff lacks Next steps on
# disk; the scope check below proves the Edit cases edit the text they name.
HS_GOAL_OLD = "Ship the handoff section check (owner message, 2026-11-08)."
HS_GOAL_NEW = "Ship the handoff section check, with its red cases (owner message, 2026-11-08)."
HS_WORK_BLOCK = "## Work in flight\n%s\n" % HS_BODIES["Work in flight"]
add("handoff-sections: an Edit that changes only the Goal of a handoff that already lacks Next steps passes, silently",
    "allow", tool="Edit", cwd=NOGIT, session=HS_GAP, config=HS_CFG, silent=True,
    file_path=hs_handoff(HS_CFG, HS_GAP), old_string=HS_GOAL_OLD, new_string=HS_GOAL_NEW)
add("handoff-sections: a MultiEdit that changes only the Goal and Where things stand of a handoff that already "
    "lacks Next steps passes, silently",
    "allow", tool="MultiEdit", cwd=NOGIT, session=HS_GAP, config=HS_CFG, silent=True,
    file_path=hs_handoff(HS_CFG, HS_GAP),
    edits=[{"old_string": HS_GOAL_OLD, "new_string": HS_GOAL_NEW},
           {"old_string": "Branch hsk-tests at", "new_string": "Branch hsk-tests2 at"}])
add("handoff-sections: an Edit that removes Work in flight from a handoff that already lacks Next steps is refused, "
    "naming Work in flight",
    "deny", HS_RULE, tool="Edit", cwd=NOGIT, session=HS_GAP, config=HS_CFG,
    carries=("Work in flight",), lacks=("Goal", "Working premises", "Where things stand", "Files and commands"),
    file_path=hs_handoff(HS_CFG, HS_GAP), old_string=HS_WORK_BLOCK, new_string="")
add("handoff-sections: a Write that lacks Next steps is refused even though the old handoff lacked it, naming Next steps",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_GAP, config=HS_CFG,
    carries=("Next steps",), lacks=("Goal", "Working premises", "Where things stand", "Work in flight",
                                    "Files and commands"),
    file_path=hs_handoff(HS_CFG, HS_GAP), content=hs_text(omit=("Next steps",)))


def hs_gap_scope():
    """The gap handoff is on disk as the fixture wrote it, with the Goal text the Edit cases replace. An Edit whose
    old text is absent is allowed by the rule, so the Edit cases prove nothing unless the file holds that text."""
    materialize(HS_CFG)
    try:
        with open(hs_handoff(HS_CFG, HS_GAP), "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as e:
        return False, "the gap handoff is unreadable: %s" % e
    if text != hs_text(omit=("Next steps",)):
        return False, "the gap handoff on disk is not the handoff without Next steps"
    if HS_GOAL_OLD not in text:
        return False, "the gap handoff lacks the Goal text the Edit cases replace"
    return True, "the gap handoff on disk lacks Next steps and holds the Goal text the Edit cases replace"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the gap handoff on disk is the one the Edit cases edit", hs_gap_scope))


# A heading numbered like the prompt's steps holds its section: `## 1. Goal`, and `# 5. Next steps` at H1. A `N)`
# heading does not: the prompt numbers its steps with `N.` only, and the premises reader reads unnumbered headings.
def hs_numbered(omit=()):
    """A handoff whose headings carry the prompt's step numbers, one `#` or `##` heading per section."""
    parts = ["# Handoff\n\n"]
    for number, name in enumerate(HS_SECTIONS, 1):
        if name not in omit:
            parts.append("%s %d. %s\n%s\n" % ("#" if name == "Next steps" else "##", number, name, HS_BODIES[name]))
    return "".join(parts)


add("handoff-sections: headings numbered like the prompt's steps count as present: a Write with `## 1. Goal` and "
    "`# 5. Next steps` passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF, content=hs_numbered())
add("handoff-sections: a numbered Write without Next steps is refused, naming Next steps only",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=("Next steps",), lacks=("Goal", "Working premises", "Where things stand", "Work in flight",
                                    "Files and commands"),
    file_path=HS_HANDOFF, content=hs_numbered(omit=("Next steps",)))
add("handoff-sections: a heading numbered `3)` is no step heading: a Write with `## 3) Where things stand` is "
    "refused, naming Where things stand only",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=("Where things stand",), lacks=("Goal", "Working premises", "Work in flight", "Next steps",
                                            "Files and commands"),
    file_path=HS_HANDOFF, content=hs_text().replace("## Where things stand\n", "## 3) Where things stand\n"))


# The rule judges only the session's handoff, <sid>.md, in the handoffs folder. The owner-feedback inbox sits beside
# it as <sid>.inbox.md and holds item lines, not sections, so a Write to it passes. Its path is local_time's, the one
# home of the inbox names.
def hs_inbox(config, session=HS_SID):
    """The session's owner-feedback inbox, as local_time.inbox_paths builds it."""
    with hu_config(config):
        return local_time.inbox_paths(session)[0]


HS_INBOX_TEXT = "### 2026-11-08 16:40 CST (UTC-06:00)\n- fb-0958-7 [page] -> page:98\n"
HS_INBOX_FULL = "### 2026-11-08 16:40 CST (UTC-06:00)\n" + "".join(
    "- fb-0958-%d [page] -> page:98\n" % n for n in range(1, 2001))


def hs_inbox_scope():
    """The inbox cases write <sid>.inbox.md beside <sid>.md in the handoffs folder: the file the rule must not judge."""
    inbox, handoff = hs_inbox(HS_CFG), hs_handoff(HS_CFG)
    if os.path.basename(inbox) != HS_SID + ".inbox.md":
        return False, "the inbox is %r, want %s.inbox.md" % (os.path.basename(inbox), HS_SID)
    if os.path.basename(handoff) != HS_SID + ".md" or os.path.dirname(inbox) != os.path.dirname(handoff):
        return False, "the inbox is not beside the session handoff in the handoffs folder"
    return True, "the inbox is <sid>.inbox.md, beside <sid>.md in the handoffs folder"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the inbox cases write <sid>.inbox.md beside the session handoff",
                         hs_inbox_scope))
add("handoff-sections: a Write to the owner-feedback inbox, item lines and no sections, passes silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=hs_inbox(HS_CFG), content=HS_INBOX_TEXT)
add("handoff-sections: an empty owner-feedback inbox passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=hs_inbox(HS_CFG), content="")
add("handoff-sections: a full-size owner-feedback inbox passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=hs_inbox(HS_CFG), content=HS_INBOX_FULL)
add("handoff-sections: control: the same item lines written to the session handoff are refused, naming all six sections",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG,
    carries=HS_SECTIONS, file_path=HS_HANDOFF, content=HS_INBOX_TEXT)


# A marker name that ends in punctuation matches its verbatim heading. The heading matcher ends each name with (?!\w):
# a `\b` after `)` or `.` needs a word character next, so `## Goal)` never matched, and the marker refused every write
# that held it.
def hs_punct_scope():
    """The punctuated fixture's installed marker names Goal) and Next steps., verbatim, so the cases below judge the
    punctuation. A marker that did not change would allow the punctuated write for the wrong reason."""
    materialize(HS_CFG_PUNCT)
    with hu_config(HS_CFG_PUNCT):
        names = ph.required_sections()
    want = [HS_PUNCT_NAMES.get(n, n) for n in HS_SECTIONS]
    if names != want:
        return False, "the installed marker reads %r, want %r" % (names, want)
    return True, "the installed marker names Goal) and Next steps. verbatim, and the other four as before"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the punctuated fixture's marker names Goal) and Next steps.",
                         hs_punct_scope))
add("handoff-sections: a marker name ending in punctuation matches its verbatim heading: a Write with `## Goal)` and "
    "`## Next steps.` passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG_PUNCT, silent=True,
    file_path=hs_handoff(HS_CFG_PUNCT), content=hs_punct_text())
add("handoff-sections: a punctuated marker still refuses a Write without its `## Next steps.` heading, naming Next steps.",
    "deny", HS_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG_PUNCT,
    carries=("Next steps.",), lacks=("Working premises", "Where things stand", "Work in flight", "Files and commands"),
    file_path=hs_handoff(HS_CFG_PUNCT), content=hs_punct_text(omit=("Next steps",)))


def hs_case(config, tool, tool_input, session=HS_SID):
    """A case dict for decide(), with each key decide() reads, built as add() builds one."""
    return {"name": "handoff-sections", "expected": None, "rule": None, "raw": None, "tool": tool,
            "cwd": NOGIT, "env_path": None, "session": session, "carries": (), "lacks": (),
            "config": config, "transcript": None, "agent_id": None, "agent_type": None, "event": None,
            "stop_active": False, "no_root": False, "max_seconds": None, "env": None, "guard": None,
            "silent": False, "temp": TEMP_DIR, "tool_input": tool_input, "family": FAMILY,
            "windows": False}


def hs_write(config, content, session=HS_SID):
    return decide(hs_case(config, "Write", {"file_path": hs_handoff(config, session),
                                            "content": content}, session))


def hs_fail_open(label, config):
    """The rule allows a drop that the intact prompt refuses, silently. The intact prompt is the control:
    without it, an allow would prove nothing, since a rule that never refuses also allows."""
    def check():
        control = hs_write(HS_CFG, hs_text(omit=HS_TAIL))
        if control[0] != "deny":
            return False, "the intact prompt does not refuse the drop: %r" % (control[0],)
        got = hs_write(config, hs_text(omit=HS_TAIL))
        if got != ("allow", ""):
            return False, "%s: the drop got %r, want a silent allow" % (label, got)
        return True, "%s: the drop is allowed silently, and the intact prompt refuses it" % label
    return check


for _label, _config in (("the prompt has no marker line", HS_CFG_NOMARK),
                        ("the prompt path is a directory", HS_CFG_DIR),
                        ("the prompt is not UTF-8", HS_CFG_BYTES)):
    LOG_CHECKS_EXTRA.append(("handoff-sections: fail open when %s" % _label, hs_fail_open(_label, _config)))


# The probe runs one guard call in-process and counts what it does: each file write (open in a write mode,
# or an os-level write) and each process start (Popen, os.system, os.spawn*). The counts go to stderr, so
# the guard's own stdout stays the decision. Bytecode writes are off, or a compiled module would hide one.
HS_PROBE = r"""
import builtins, io, json, os, runpy, subprocess, sys
guard, payload, watch = sys.argv[1], sys.argv[2], sys.argv[3]
seen = {"writes": [], "starts": [], "reads": []}
real_open = builtins.open


def counted_open(file, mode="r", *args, **kwargs):
    if any(c in str(mode) for c in "wax+"):
        seen["writes"].append(os.path.basename(str(file)))
    elif watch and os.path.basename(str(file)) == watch:
        seen["reads"].append(watch)
    return real_open(file, mode, *args, **kwargs)


builtins.open = counted_open
io.open = counted_open


class CountingPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        seen["starts"].append("Popen")
        super().__init__(*args, **kwargs)


subprocess.Popen = CountingPopen


def counted(bucket, name, real):
    def call(*args, **kwargs):
        # A folder call that finds the folder already there changes nothing, so it is no write.
        if name in ("makedirs", "mkdir") and args and os.path.exists(args[0]):
            return real(*args, **kwargs)
        seen[bucket].append("os." + name)
        return real(*args, **kwargs)
    return call


for name in ("remove", "unlink", "rename", "replace", "makedirs", "mkdir", "rmdir", "utime", "truncate",
             "chmod"):
    if hasattr(os, name):
        setattr(os, name, counted("writes", name, getattr(os, name)))
for name in ("system", "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
             "startfile"):
    if hasattr(os, name):
        setattr(os, name, counted("starts", name, getattr(os, name)))
sys.path.insert(0, os.path.dirname(os.path.abspath(guard)))
sys.argv = [guard]
sys.stdin = io.StringIO(payload)
code = 0
try:
    runpy.run_path(guard, run_name="__main__")
except SystemExit as e:
    code = e.code
finally:
    sys.stderr.write("HS_COST " + json.dumps(seen) + "\n")
sys.exit(code)
"""


def hs_probe(config, tool, tool_input, session=HS_SID, transcript=None):
    """One guard call under HS_PROBE. Returns (decision, reason, writes, starts, reads), or None for the counts
    when the probe printed none (the probe itself failed, so the counts prove nothing). `transcript`, when
    given, is the payload's transcript_path; `reads` counts each read of that file."""
    materialize(config)   # the config folder's installed prompt, built before the guard reads it
    if transcript:
        materialize(transcript)
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_REMOTE", "PYTHONPATH", "CLAUDE_CODE_SESSION_ID",
                 "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
        env.pop(name, None)
    env["CLAUDE_CONFIG_DIR"] = config
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    body = {"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT, "session_id": session}
    if transcript:
        body["transcript_path"] = transcript
    watch = os.path.basename(transcript) if transcript else ""
    run = subprocess.run([sys.executable, "-c", HS_PROBE, GUARD, json.dumps(body), watch],
                         capture_output=True, text=True, env=env, timeout=120)
    counts = None
    for line in run.stderr.splitlines():
        if line.startswith("HS_COST "):
            counts = json.loads(line[len("HS_COST "):])
    decision, reason = read_decision(run.stdout)
    if counts is None:
        return decision, reason, None, None, None
    return decision, reason, counts["writes"], counts["starts"], counts["reads"]


def hs_cost_check():
    """A call the rule allows writes no file and starts no process. A refusal writes its guard.log line and
    starts no process. The control is a refusal the guard already makes (git-env-set): a probe that counts
    nothing would also show zero writes, so the control must show the refusal's log line."""
    control = hs_probe(HS_CFG, "Bash", {"command": "GIT_DIR=/nowhere " + VCS + " status"})
    if control[2] is None:
        return False, "the probe printed no count for the control call"
    if control[0] != "deny" or control[2] != ["guard.log"]:
        return False, "the control refusal gave %r with writes %r, want deny with one guard.log write" % (
            control[0], control[2])
    allowed = hs_probe(HS_CFG, "Write", {"file_path": hs_handoff(HS_CFG), "content": hs_text()})
    if allowed[2] is None:
        return False, "the probe printed no count for an allowed handoff Write"
    if allowed[0] != "allow" or allowed[1]:
        return False, "a complete handoff Write gave %r, want a silent allow" % (allowed[0],)
    if allowed[2] or allowed[3]:
        return False, "an allowed handoff Write made writes %r and starts %r, want none" % (
            allowed[2], allowed[3])
    refused = hs_probe(HS_CFG, "Write", {"file_path": hs_handoff(HS_CFG), "content": hs_text(omit=HS_TAIL)})
    if refused[2] is None:
        return False, "the probe printed no count for a refused handoff Write"
    if refused[0] != "deny":
        return False, "a handoff Write that drops three sections gave %r, want deny" % (refused[0],)
    if refused[2] != ["guard.log"] or refused[3]:
        return False, "a refused handoff Write wrote %r and started %r, want one guard.log write and no start" % (
            refused[2], refused[3])
    return True, "an allowed handoff Write writes no file and starts no process; a refusal writes its guard.log line only"


LOG_CHECKS_EXTRA.append(("handoff-sections: an allowed write writes no file and starts no process; a refusal "
                         "writes its guard.log line only", hs_cost_check))


# =========================================================================== handoff-checked-stamp
# A write to a session handoff that restamps a premise's `Checked` value needs evidence in the session's own transcript: a
# tool_use, after the last compact_boundary record, whose input holds a token of that premise's Source. A restamp with no
# evidence is refused, and the reason names each such premise and its token. The rule judges the same (before, after) text
# as handoff-sections, and the before is the handoff on disk. Cost: the transcript is read at most once, and not at all
# when no stamp changed; a call it allows writes no file and starts no process; a refusal writes its guard.log line only.
#
# Every case that allows a write holds a control: the same write with no evidence, which the rule must refuse. The control
# comes first, so a guard without the rule fails on the control's missing deny, and the allowed call proves nothing alone.
