# section 38287
FAMILY = "handoff-sections"
HS_RULE = "handoff-sections"
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
# A full-size handoff under the size limit: 34895 UTF-8 bytes, 9970 estimated tokens, against the 10000-token limit
# (decision precompact-handoff, limit set 19:07 CST Nov 23, 2026). Above the limit, handoff-too-big refuses it.
add("handoff-sections: a full-size handoff that keeps all six sections passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=HS_HANDOFF,
    content=HS_FULL.replace(HS_BODIES["Where things stand"],
                            "Branch hsk-tests at 2ac382cc6.\n" + "A line of state, kept.\n" * 1500))
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


# ------------------------------------------------------------------------------------- Bash writes to the session handoff
# A Bash call that puts content on the session handoff is judged as a write of that content when the command names it: a
# readable file (cp, mv, cat of a file), a heredoc, or literal text in python3 -c. Content that a program or computed code
# makes is unknown before the command runs, so that call is refused with the Write tool as the remedy, under HSW_RULE
# (the owner may reverse this pick). The size and checked-stamp families hold the same command shapes for their rules.
# The ~ and $HOME forms run with HOME set to ROOT, so they name the fixture's home and nothing outside it.
HSW_RULE = "handoff-shell-write"
HSW_REMEDY = "Write tool"
HBW_DIR = os.path.join(ROOT, "hbw")                  # the scratch files a Bash call copies from
HBW_NOSEC = os.path.join(HBW_DIR, "nosec.md")        # a handoff that drops the tail, under the size limit
HBW_GOOD = os.path.join(HBW_DIR, "good.md")          # a handoff with all six sections, under the size limit
HBW_OUT = os.path.join(HBW_DIR, "out.md")            # where a read-out copies the handoff; no case writes it
HBW_KEEP = ("Goal", "Working premises", "Where things stand")   # the three a tail-cut handoff keeps
HBW_HOME_REL = os.path.relpath(HS_HANDOFF, ROOT).replace(os.sep, "/")   # hs-cfg/handoffs/<HS_SID>.md
HBW_TILDE = "~/" + HBW_HOME_REL
HBW_DOLLAR = "$HOME/" + HBW_HOME_REL
HBW_HOME = {"HOME": ROOT}                            # the env that makes ~ and $HOME name the fixture's home
HBW_OTHER = hs_handoff(HS_CFG, HS_OTHER)             # another session's handoff in the same config folder
HBW_INBOX = hs_inbox(HS_CFG)                         # the session's owner-feedback inbox, beside its handoff


def _build_hbw():
    write(HBW_NOSEC, hs_text(omit=HS_TAIL))
    write(HBW_GOOD, hs_text())


lazy_fixture([HBW_NOSEC, HBW_GOOD], _build_hbw)
HS_FOLDER = os.path.dirname(HS_HANDOFF)                                 # the handoffs folder: a folder target names it
HBW_NAMED = os.path.join(ROOT, "hbw-named", HS_SID + ".md")             # drops the tail, named as the session handoff
HBW_NAMED_GOOD = os.path.join(ROOT, "hbw-named-good", HS_SID + ".md")   # all six sections, under the same name
HBW_CFG_VAR_HANDOFF = "\"$CLAUDE_CONFIG_DIR/handoffs/%s.md\"" % HS_SID  # the session handoff, through the config variable
# A case-insensitive volume reads one folder under two spellings. The probe runs on this run's volume, which HS_CFG sits on:
# where the capitals spelling is the same folder, a Bash write to it is a write to the session handoff. Where it is another
# folder, that case is skipped and says why.
CASE_DIR = os.path.join(ROOT, "case-probe")
os.makedirs(os.path.join(CASE_DIR, "handoffs"), exist_ok=True)
try:
    CASE_INSENSITIVE = os.path.samefile(os.path.join(CASE_DIR, "HANDOFFS"), os.path.join(CASE_DIR, "handoffs"))
except OSError:
    CASE_INSENSITIVE = False
HS_CASE_HANDOFF = os.path.join(HS_CFG, "HANDOFFS", HS_SID + ".md")      # the session handoff, its folder in capitals


def _build_hbw_named():
    write(HBW_NAMED, hs_text(omit=HS_TAIL))
    write(HBW_NAMED_GOOD, hs_text())


lazy_fixture([HBW_NAMED, HBW_NAMED_GOOD], _build_hbw_named)


def hbw_home_expands(rel, want):
    """(ok, tilde, dollar): with HOME set to ROOT, `~/rel` and `$HOME/rel` each expand to `want`. The guard reads HOME
    from its environment, so the case's env sets it the same way."""
    saved = os.environ.get("HOME")
    os.environ["HOME"] = ROOT
    try:
        tilde = os.path.expanduser("~/" + rel)
        dollar = os.path.expandvars("$HOME/" + rel)
    finally:
        if saved is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved
    return tilde == want and dollar == want, tilde, dollar


def hbw_scope():
    """The Bash cases copy the scratch file on disk, and read the ~ and $HOME forms as the session handoff under HOME. A
    scratch file that differs from its text, or a form that names another path, would move a verdict with no other check
    failing."""
    materialize(HBW_NOSEC)
    try:
        with open(HBW_NOSEC, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as e:
        return False, "the scratch file is unreadable: %s" % e
    if text != hs_text(omit=HS_TAIL):
        return False, "the scratch file on disk is not the handoff without the tail"
    ok, tilde, dollar = hbw_home_expands(HBW_HOME_REL, hs_handoff(HS_CFG))
    if not ok:
        return False, "with HOME at the fixture root, ~ names %s and $HOME names %s" % (tilde, dollar)
    return True, "the scratch file drops the tail, and ~ and $HOME name the session handoff under the fixture root"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the Bash scratch file drops the tail, and ~ and $HOME name the session "
                         "handoff", hbw_scope))


def hbw_refuse(name, command, rule=HS_RULE, carries=HS_TAIL, lacks=HBW_KEEP, **kw):
    """One Bash call the rule refuses: the deny, its rule, and the fragments its reason names and does not name."""
    sh(name, command, "deny", rule, cwd=NOGIT, session=HS_SID, config=HS_CFG, carries=carries, lacks=lacks, **kw)


def hbw_allow(name, command, **kw):
    """One Bash call that passes silently: a control, or a write whose content the rules judge good."""
    sh(name, command, "allow", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True, **kw)


HBW_PY = "python3 -c \"open('%s', 'w').write('''%s''')\""   # a literal, multi-line text written by python3 -c
HBW_NOSEC_TEXT = hs_text(omit=HS_TAIL)
HBW_GOOD_TEXT = hs_text()

hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail onto the session handoff is refused, "
         "naming the three",
         "cp %s %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a Bash mv of a scratch file that drops the tail onto the session handoff is refused, "
         "naming the three",
         "mv %s %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a Bash cat of a scratch file redirected onto the session handoff is refused, naming the three",
         "cat %s > %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a heredoc redirected with > onto the session handoff, dropping the tail, is refused, "
         "naming the three",
         "cat > %s <<'EOF'\n%sEOF\n" % (HS_HANDOFF, HBW_NOSEC_TEXT))
hbw_refuse("handoff-sections: a tee of a heredoc onto the session handoff, dropping the tail, is refused, naming the three",
         "tee %s <<'EOF'\n%sEOF\n" % (HS_HANDOFF, HBW_NOSEC_TEXT))
hbw_refuse("handoff-sections: a python3 -c that writes a literal handoff dropping the tail onto the session handoff is "
         "refused, naming the three",
         HBW_PY % (HS_HANDOFF, HBW_NOSEC_TEXT))
hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail, written with ~, is refused, naming the three",
         "cp %s %s" % (HBW_NOSEC, HBW_TILDE), env=HBW_HOME)
hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail, written with $HOME, is refused, naming "
         "the three",
         "cp %s %s" % (HBW_NOSEC, HBW_DOLLAR), env=HBW_HOME)
hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail onto another session's handoff is refused, "
         "naming the three",
         "cp %s %s" % (HBW_NOSEC, HBW_OTHER))

# The controls: each is the same shape as a refused call above, with a target or content the rules pass.
hbw_allow("handoff-sections: a Bash cp of a complete scratch file onto the session handoff passes, silently",
          "cp %s %s" % (HBW_GOOD, HS_HANDOFF))
hbw_allow("handoff-sections: a heredoc redirected with > onto the session handoff, keeping all six sections, passes, silently",
          "cat > %s <<'EOF'\n%sEOF\n" % (HS_HANDOFF, HBW_GOOD_TEXT))
hbw_allow("handoff-sections: a tee of a heredoc onto the session handoff, keeping all six sections, passes, silently",
          "tee %s <<'EOF'\n%sEOF\n" % (HS_HANDOFF, HBW_GOOD_TEXT))
hbw_allow("handoff-sections: a python3 -c that writes a literal handoff keeping all six sections passes, silently",
          HBW_PY % (HS_HANDOFF, HBW_GOOD_TEXT))
hbw_allow("handoff-sections: a Bash cp of a complete scratch file onto another session's handoff passes, silently",
          "cp %s %s" % (HBW_GOOD, HBW_OTHER))
hbw_allow("handoff-sections: a Bash append of a complete scratch file to the session handoff keeps all six sections, "
          "and passes, silently",
          "cat %s >> %s" % (HBW_GOOD, HS_HANDOFF))
hbw_allow("handoff-sections: a read-out cp of the session handoff to a scratch file passes, silently",
          "cp %s %s" % (HS_HANDOFF, HBW_OUT))
hbw_allow("handoff-sections: a cat of the session handoff passes, silently", "cat %s" % HS_HANDOFF)
hbw_allow("handoff-sections: a wc of the session handoff passes, silently", "wc -l %s" % HS_HANDOFF)
hbw_allow("handoff-sections: a grep of the session handoff passes, silently",
          "grep -n 'Next steps' %s" % HS_HANDOFF)
hbw_allow("handoff-sections: a command that only names the session handoff in an echo string passes, silently",
          "echo \"cp %s %s\"" % (HBW_NOSEC, HS_HANDOFF))
hbw_allow("handoff-sections: an item-line heredoc appended to the owner-feedback inbox passes, silently",
          "cat >> %s <<'EOF'\n%sEOF\n" % (HBW_INBOX, HS_INBOX_TEXT))
hbw_refuse("handoff-sections: the same item lines redirected with > onto the session handoff are refused, naming all six",
         "cat > %s <<'EOF'\n%sEOF\n" % (HS_HANDOFF, HS_INBOX_TEXT), carries=HS_SECTIONS, lacks=())

# A pipe from a program, or python3 -c with computed text, puts content on the handoff the guard cannot read before the
# command runs. The call is refused under HSW_RULE, and the remedy names the Write tool.
HSW_LACKS = HS_SECTIONS
hbw_refuse("handoff-shell-write: a pipe from git into tee onto the session handoff is refused, with the Write tool as "
         "the remedy",
         VCS + " log --oneline | tee %s" % HS_HANDOFF,
         rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-shell-write: a python3 -c that writes computed text onto the session handoff is refused, with the "
         "Write tool as the remedy",
         "python3 -c \"open('%s', 'w').write('A' * 40000)\"" % HS_HANDOFF,
         rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-shell-write: a pipe from git into tee onto the session handoff, written with ~, is refused, with the "
         "Write tool as the remedy",
         VCS + " log --oneline | tee " + HBW_TILDE, env=HBW_HOME,
         rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-shell-write: a pipe from git into tee onto the session handoff, written with $HOME, is refused, with "
         "the Write tool as the remedy",
         VCS + " log --oneline | tee " + HBW_DOLLAR, env=HBW_HOME,
         rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)


# ----------------------------------------------------------------- Bash forms that put a session handoff's text on disk
# Judged as a Write of the same text: a source that is a readable file is refused under the rule its content breaks (a file
# that drops the tail, handoff-sections). perl -pi -e rewrites the file with a program's text, which the guard cannot read
# before the command runs, so it is refused under handoff-shell-write. The cd and shell-variable forms are judged already
# and are pinned here, so a change to the readers keeps them.
def hbw_named_scope():
    """The folder forms copy a file named as the session handoff, so the copy lands on the handoff itself. The no-slash form
    needs the folder to exist on disk. A file under another name, or a missing folder, would move those cases to another
    target with no other check failing."""
    materialize(HS_CFG)
    if not os.path.isdir(HS_FOLDER):
        return False, "the handoffs folder is not on disk, so a cp with no slash would not name it"
    for path, want in ((HBW_NAMED, hs_text(omit=HS_TAIL)), (HBW_NAMED_GOOD, hs_text())):
        if os.path.basename(path) != os.path.basename(HS_HANDOFF):
            return False, "%s is not named as the session handoff" % os.path.basename(path)
        materialize(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as e:
            return False, "%s is unreadable: %s" % (path, e)
        if text != want:
            return False, "%s on disk is not the text the cases name" % path
    return True, "the folder forms' scratch files are named as the session handoff, and the handoffs folder is on disk"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the folder forms' scratch files are named as the session handoff",
                         hbw_named_scope))

hbw_refuse("handoff-sections: a Bash cp of a scratch file named as the session handoff, into the handoffs folder with a "
           "trailing slash, is refused, naming the three",
           "cp %s %s/" % (HBW_NAMED, HS_FOLDER))
hbw_refuse("handoff-sections: a Bash cp of a scratch file named as the session handoff, into the handoffs folder with no "
           "slash, is refused, naming the three",
           "cp %s %s" % (HBW_NAMED, HS_FOLDER))
hbw_refuse("handoff-sections: a Bash cp -t of a scratch file named as the session handoff, into the handoffs folder, is "
           "refused, naming the three",
           "cp -t %s %s" % (HS_FOLDER, HBW_NAMED))
hbw_refuse("handoff-sections: a Bash noclobber-override redirect >| of a scratch file that drops the tail onto the session "
           "handoff is refused, naming the three",
           "cat %s >| %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a Bash dd of a scratch file that drops the tail, with of= the session handoff, is refused, "
           "naming the three",
           "dd if=%s of=%s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a Bash rsync of a scratch file that drops the tail onto the session handoff is refused, "
           "naming the three",
           "rsync %s %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a Bash ditto of a scratch file that drops the tail onto the session handoff is refused, "
           "naming the three",
           "ditto %s %s" % (HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-sections: a cd into the handoffs folder, then a cp of a scratch file that drops the tail onto the bare "
           "file name, is refused, naming the three",
           "cd %s && cp %s %s.md" % (HS_FOLDER, HBW_NOSEC, HS_SID))
hbw_refuse("handoff-sections: a cd into the handoffs folder, then a > redirect of a scratch file that drops the tail onto "
           "the bare file name, is refused, naming the three",
           "cd %s && cat %s > %s.md" % (HS_FOLDER, HBW_NOSEC, HS_SID))
hbw_refuse("handoff-sections: a cp of a scratch file that drops the tail onto the session handoff, its path held in a shell "
           "variable set earlier on the line, is refused, naming the three",
           "H=%s && cp %s \"$H\"" % (HS_HANDOFF, HBW_NOSEC))
hbw_refuse("handoff-sections: a cp of a scratch file that drops the tail onto the session handoff, its path held in a shell "
           "variable set with a semicolon, is refused, naming the three",
           "H=%s; cp %s $H" % (HS_HANDOFF, HBW_NOSEC))
hbw_refuse("handoff-sections: a cp of a scratch file that drops the tail to $CLAUDE_CONFIG_DIR/handoffs/<session>.md, the "
           "variable set in the payload's environment, is refused, naming the three",
           "cp %s %s" % (HBW_NOSEC, HBW_CFG_VAR_HANDOFF))
if CASE_INSENSITIVE:
    hbw_refuse("handoff-sections: a cp of a scratch file that drops the tail onto the session handoff, named in the handoffs "
               "folder's capitals spelling, which is the same folder on this volume, is refused, naming the three",
               "cp %s %s" % (HBW_NOSEC, HS_CASE_HANDOFF))
else:
    skip_case("handoff-sections: a cp into the handoffs folder spelled in capitals is refused, naming the three",
              "this volume is case-sensitive, so the capitals spelling is another folder, not the session handoff")
hbw_refuse("handoff-shell-write: a perl -pi -e that rewrites the session handoff in place is refused, with the Write tool as "
           "the remedy",
           "perl -pi -e 's/Goal/Goal/' %s" % HS_HANDOFF,
           rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)

# The controls: each is the same shape as a refused form above, with a target or content the rules pass.
hbw_allow("handoff-sections: a Bash cp of a complete scratch file named as the session handoff, into the handoffs folder "
          "with a trailing slash, passes, silently",
          "cp %s %s/" % (HBW_NAMED_GOOD, HS_FOLDER))
hbw_allow("handoff-sections: a Bash cp of a complete scratch file to $CLAUDE_CONFIG_DIR/handoffs/<session>.md passes, "
          "silently",
          "cp %s %s" % (HBW_GOOD, HBW_CFG_VAR_HANDOFF))
hbw_allow("handoff-sections: a printf appended with > to the session's owner-feedback inbox passes, silently",
          "printf 'item\\n' >> %s" % HBW_INBOX)
hbw_allow("handoff-sections: a printf piped into tee -a on the session's owner-feedback inbox passes, silently",
          "printf 'item\\n' | tee -a %s" % HBW_INBOX)
hbw_allow("handoff-sections: an rsync of a handoff that lacks Next steps out to a scratch folder passes, silently",
          "rsync %s %s/" % (hs_handoff(HS_CFG, HS_GAP), HBW_DIR))
hbw_allow("handoff-sections: a cp of a scratch file that drops the tail into a folder elsewhere whose name contains handoffs "
          "passes, silently",
          "cp %s %s" % (HBW_NOSEC, os.path.join(HBW_DIR, "handoffs-archive", HS_SID + ".md")))
sh("handoff-sections: the audit brief run of the session handoff, python3 on the installed script, passes, silently",
   "python3 %s --audit-brief --handoff %s" % (os.path.join(HERE, "precompact_handoff.py"), HS_HANDOFF), "allow",
   cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True)


# ----------------------------------------------------------------- Bash sources a call writes, and the default-value path
# A source that any segment of the same call writes is unknown: the guard reads it from disk before the call runs, so the
# disk text is not the text that lands on the handoff. Such a call is refused under handoff-shell-write, with the Write tool
# as the remedy. The controls are the same writes without the copy onto the handoff.
HBW_PRINTED = os.path.join(HBW_DIR, "printed.md")     # a complete handoff on disk, which the call's printf overwrites
HBW_STALE = os.path.join(HBW_DIR, "stale.md")         # a handoff that drops the tail on disk, which the call copies over
HBW_MOVED = os.path.join(HBW_DIR, "moved-out.md")     # where a moved handoff goes; no case writes it


def _build_hbw_sources():
    write(HBW_PRINTED, hs_text())
    write(HBW_STALE, hs_text(omit=HS_TAIL))


lazy_fixture([HBW_PRINTED, HBW_STALE], _build_hbw_sources)


def hbw_sources_scope():
    """The source cases name their scratch files by what is on disk: a complete handoff under the printf case's name, and a
    handoff that drops the tail under the stale copy's. Other text would move a verdict with no other check failing."""
    for path, want in ((HBW_PRINTED, hs_text()), (HBW_STALE, hs_text(omit=HS_TAIL))):
        materialize(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as e:
            return False, "%s is unreadable: %s" % (os.path.basename(path), e)
        if text != want:
            return False, "%s on disk is not the text the case names" % os.path.basename(path)
    return True, "the printf case's scratch file is a complete handoff, and the stale copy's drops the tail"


LOG_CHECKS_EXTRA.append(("handoff-sections: scope: the source cases' scratch files hold the text each case names",
                         hbw_sources_scope))

hbw_refuse("handoff-shell-write: a Bash printf that overwrites a scratch file, then a cp of that file onto the session handoff, "
           "is refused, with the Write tool as the remedy",
           "printf 'x' > %s && cp %s %s" % (HBW_PRINTED, HBW_PRINTED, HS_HANDOFF),
           rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-shell-write: a Bash cp of a good file over a scratch file that holds a handoff dropping the tail, then a cp "
           "of that scratch file onto the session handoff, is refused under handoff-shell-write, with the Write tool as the remedy",
           "cp %s %s && cp %s %s" % (HBW_GOOD, HBW_STALE, HBW_STALE, HS_HANDOFF),
           rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_allow("handoff-sections: a Bash printf over a scratch file that no handoff names passes, silently",
          "printf 'x' > %s" % HBW_PRINTED)
hbw_allow("handoff-sections: a Bash cp of a good file over a scratch file that holds a stale handoff, with no copy onto the "
          "session handoff, passes, silently",
          "cp %s %s" % (HBW_GOOD, HBW_STALE))

# False alarms. Each call touches the session handoff without writing its text. The guard on main allows every one of them;
# the head refuses the first five under handoff-shell-write, which the pins below hold to allow.
hbw_allow("handoff-sections: a Bash rm of the session handoff passes, silently", "rm %s" % HS_HANDOFF)
hbw_allow("handoff-sections: a Bash rm -f of the handoffs folder's .md files passes, silently", "rm -f %s/*.md" % HS_FOLDER)
hbw_allow("handoff-sections: a Bash mv of the session handoff to another folder passes, silently",
          "mv %s %s" % (HS_HANDOFF, HBW_MOVED))
hbw_allow("handoff-sections: a Bash mv of the session handoff to a .bak name passes, silently",
          "mv %s %s.bak" % (HS_HANDOFF, HS_HANDOFF))
hbw_allow("handoff-sections: a Bash chmod 600 of the session handoff passes, silently", "chmod 600 %s" % HS_HANDOFF)
hbw_allow("handoff-sections: an echo of a string that holds rm and the session handoff's path passes, silently",
          "echo \"rm %s\"" % HS_HANDOFF)

# The default-value path. ${CLAUDE_CONFIG_DIR:-$HOME/.claude} names the session handoff with the variable set (the config
# folder is HS_CFG) and with it unset (HOME is the fixture home, whose .claude is HBD_CFG). Each call is judged like the
# plain path. HBD_CFG holds an installed prompt, so a refusal there is the rule's, not a missing prompt's.
HBD_HOME = os.path.join(ROOT, "hbd-home")             # the fixture home; its .claude is the config folder below
HBD_CFG = os.path.join(HBD_HOME, ".claude")           # the installed prompt and a session handoff, as HS_CFG holds
HBD_HANDOFF = hs_handoff(HBD_CFG)                     # the plain path to the session handoff under HBD_CFG
HBD_ENV = {"CLAUDE_CONFIG_DIR": None, "HOME": HBD_HOME}   # the variable unset, and HOME at the fixture home
HBD_ENV_WIN = dict(HBD_ENV, USERPROFILE=HBD_HOME)   # the same, and USERPROFILE too: Windows' ~ reads it, not HOME
HBD_DEFAULT = "\"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/handoffs/%s.md\"" % HS_SID


def _build_hbd():
    hs_install(HBD_CFG, hs_prompt_text())
    write(HBD_HANDOFF, HS_FULL)


lazy_fixture([HBD_CFG], _build_hbd)

hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail to the default-value path, with the variable "
           "set, is refused, naming the three",
           "cp %s %s" % (HBW_NOSEC, HBD_DEFAULT))
hbw_refuse("handoff-sections: a Bash > redirect of a scratch file that drops the tail to the default-value path, with the "
           "variable set, is refused, naming the three",
           "cat %s > %s" % (HBW_NOSEC, HBD_DEFAULT))
hbw_allow("handoff-sections: a Bash cp of a complete scratch file to the default-value path, with the variable set, passes, "
          "silently",
          "cp %s %s" % (HBW_GOOD, HBD_DEFAULT))
hbw_allow("handoff-sections: a Bash > redirect of a complete scratch file to the default-value path, with the variable set, "
          "passes, silently",
          "cat %s > %s" % (HBW_GOOD, HBD_DEFAULT))
sh("handoff-sections: a Bash cp of a scratch file that drops the tail to the default-value path, with the variable unset, "
   "is refused, naming the three",
   "cp %s %s" % (HBW_NOSEC, HBD_DEFAULT), "deny", HS_RULE, cwd=NOGIT, session=HS_SID, config=HBD_CFG, env=HBD_ENV_WIN,
   carries=HS_TAIL, lacks=HBW_KEEP)
sh("handoff-sections: a Bash > redirect of a scratch file that drops the tail to the default-value path, with the variable "
   "unset, is refused, naming the three",
   "cat %s > %s" % (HBW_NOSEC, HBD_DEFAULT), "deny", HS_RULE, cwd=NOGIT, session=HS_SID, config=HBD_CFG, env=HBD_ENV_WIN,
   carries=HS_TAIL, lacks=HBW_KEEP)
sh("handoff-sections: a Bash cp of a complete scratch file to the default-value path, with the variable unset, passes, "
   "silently",
   "cp %s %s" % (HBW_GOOD, HBD_DEFAULT), "allow", cwd=NOGIT, session=HS_SID, config=HBD_CFG, env=HBD_ENV, silent=True)
sh("handoff-sections: a Bash > redirect of a complete scratch file to the default-value path, with the variable unset, "
   "passes, silently",
   "cat %s > %s" % (HBW_GOOD, HBD_DEFAULT), "allow", cwd=NOGIT, session=HS_SID, config=HBD_CFG, env=HBD_ENV, silent=True)
sh("handoff-sections: a Bash cp of a scratch file that drops the tail to the plain path under the fixture home's config is "
   "refused, naming the three",
   "cp %s %s" % (HBW_NOSEC, HBD_HANDOFF), "deny", HS_RULE, cwd=NOGIT, session=HS_SID, config=HBD_CFG,
   carries=HS_TAIL, lacks=HBW_KEEP)
hbw_refuse("handoff-sections: a Bash cp of a scratch file that drops the tail to the braces form, ${CLAUDE_CONFIG_DIR}, is "
           "refused, naming the three",
           "cp %s \"${CLAUDE_CONFIG_DIR}/handoffs/%s.md\"" % (HBW_NOSEC, HS_SID))


# ------------------------------------------------- an excused segment and a real write in one call
# A segment that is one rm, chmod, touch or mv of the session handoff puts no text on it, so the guard excuses that
# segment. The excuse covers that segment alone: a real write onto the handoff in another segment of the same call is
# judged as it is judged alone. The four refusals below are pins of current behaviour. The tee reads its source
# through `<`, which the guard does not read as a file copy, so its text is unknown and it is refused under
# handoff-shell-write. The last call is the control: the same excused segment, with a complete handoff copied in, passes.
hbw_refuse("handoff-sections: a Bash rm of the session handoff, then a cp of a scratch file that drops the tail onto it, "
           "is refused, naming the three",
           "rm %s && cp %s %s" % (HS_HANDOFF, HBW_NOSEC, HS_HANDOFF))
hbw_refuse("handoff-shell-write: a Bash touch of the session handoff, then a printf redirect onto it, is refused, with "
           "the Write tool as the remedy",
           "touch %s && printf 'x' > %s" % (HS_HANDOFF, HS_HANDOFF),
           rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-shell-write: a Bash chmod 600 of the session handoff, then a tee of a scratch file onto it, is refused, "
           "with the Write tool as the remedy",
           "chmod 600 %s && tee %s < %s" % (HS_HANDOFF, HS_HANDOFF, HBW_NOSEC),
           rule=HSW_RULE, carries=(HSW_REMEDY,), lacks=HSW_LACKS)
hbw_refuse("handoff-sections: a cd into the handoffs folder, an rm of the session handoff by its bare name, then a cp of "
           "a scratch file that drops the tail onto that name, is refused, naming the three",
           "cd %s && rm %s.md && cp %s %s.md" % (HS_FOLDER, HS_SID, HBW_NOSEC, HS_SID))
hbw_allow("handoff-sections: a Bash rm of the session handoff, then a cp of a complete scratch file onto it, passes, silently",
          "rm %s && cp %s %s" % (HS_HANDOFF, HBW_GOOD, HS_HANDOFF))


# =========================================================================== handoff-checked-stamp
# A write to a session handoff that restamps a premise's `Checked` value needs evidence in the session's own transcript: a
# tool_use, after the last compact_boundary record, whose input holds a token of that premise's Source. A restamp with no
# evidence is refused, and the reason names each such premise and its token. The rule judges the same (before, after) text
# as handoff-sections, and the before is the handoff on disk. Cost: the transcript is read at most once, and not at all
# when no stamp changed; a call it allows writes no file and starts no process; a refusal writes its guard.log line only.
#
# Every case that allows a write holds a control: the same write with no evidence, which the rule must refuse. The control
# comes first, so a guard without the rule fails on the control's missing deny, and the allowed call proves nothing alone.
