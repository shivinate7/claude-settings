# section 38816
FAMILY = "handoff-checked-stamp"
HCS_RULE = "handoff-checked-stamp"
HCS_SID = "4b8e1d62-0000-4000-8000-00000000c0a1"       # the session that restamps
HCS_SID_FULL = "4b8e1d62-0000-4000-8000-00000000f0a1"  # a full-size handoff, in the same config folder
HCS_CFG = os.path.join(ROOT, "hcs-cfg")                # the installed prompt, and both session handoffs
HCS_CFG_DIR = os.path.join(ROOT, "hcs-dir")            # the prompt path is a directory
HCS_TX = os.path.join(ROOT, "hcs-tx")                  # the transcripts
HCS_WT = "/work/checkout"                              # the checkout that the transcripts' paths name
HCS_OLD = "2026-11-07"
HCS_NEW = "2026-11-09"
# (id, kind, statement, source). Every Source holds one token (a path, a commit, a backticked command) except P7 and P9,
# which hold none. P8 is left out on purpose: a case adds it as a new line.
HCS_ROWS = (
    ("P1", "read", "The guard judges each handoff write", "hooks/precompact_handoff.py:279"),
    ("P2", "read", "The premise kinds run strongest first", "docs/decisions/premise-format.md:12"),
    ("P3", "read", "The base commit is the origin main head", "commit 624dcc188"),
    ("P4", "read", "The digest reads the transcript once", "hooks/reread_check.py:40"),
    ("P5", "measured", "The git revision is the base", "`git rev-parse --short HEAD`"),
    ("P6", "ruling", "Premises are statements, not facts", "owner, 2026-10-21"),
    ("P7", "assumed", "The handoff keeps the Goal", "the compaction summary"),
    ("P9", "notes", "The owner wants the rule", "the owner's note (see # 12 and // 3)"),
)
HCS_FILLER = tuple(("P%d" % n, "notes", "Filler fact %d, kept for the full-size handoff" % n, "the compaction summary")
                   for n in range(10, 17))
HCS_FULL_ROWS = HCS_ROWS + HCS_FILLER   # 15 premises: the most a handoff holds


def hcs_line(row, checked):
    pid, kind, statement, source = row
    return "- %s [%s] %s. Source: %s. Checked %s." % (pid, kind, statement, source, checked)


def hcs_row(pid, checked, rows=HCS_ROWS):
    """The premise line of `pid` at `checked`: the text an Edit replaces, or the text it writes."""
    return hcs_line([r for r in rows if r[0] == pid][0], checked)


def hcs_lines(rows=HCS_ROWS, new=(), value=HCS_NEW, reword=None, extra=()):
    """The premise lines of a handoff: each row at the old stamp, and each id in `new` at `value`. `reword` is a pair
    (id, statement) that changes one statement and keeps its stamp. `extra` adds lines after the rows."""
    lines = []
    for pid, kind, statement, source in rows:
        if reword and reword[0] == pid:
            statement = reword[1]
        lines.append(hcs_line((pid, kind, statement, source), value if pid in new else HCS_OLD))
    return lines + list(extra)


def hcs_text(rows=HCS_ROWS, new=(), value=HCS_NEW, reword=None, extra=()):
    """A whole handoff whose Working premises body is hcs_lines(...). Every other section is hs_text's."""
    return hs_text(premises=hcs_lines(rows, new, value, reword, extra))


HCS_OLD_TEXT = hcs_text()                                  # the handoff on disk: every stamp old
HCS_FULL_TEXT = hcs_text(rows=HCS_FULL_ROWS)               # the same, at 15 premises
HCS_T_P1 = hcs_text(new=("P1",))
HCS_T_P1_P2 = hcs_text(new=("P1", "P2"))
HCS_T_P1_P5 = hcs_text(new=("P1", "P5"))
HCS_T_P2_P3 = hcs_text(new=("P2", "P3"))
HCS_T_INCIDENT = hcs_text(new=("P1", "P2", "P3", "P4", "P5"))
HCS_T_P6 = hcs_text(new=("P6",))
HCS_T_P7 = hcs_text(new=("P7",))
HCS_T_P9 = hcs_text(new=("P9",))
HCS_T_NEVER_P1 = hcs_text(new=("P1",), value="never")
HCS_T_REWORD = hcs_text(reword=("P2", "The premise kinds run strongest first, as the table says"))
HCS_T_FULL_P12 = hcs_text(rows=HCS_FULL_ROWS, new=("P12",))
HCS_P8 = ("P8", "read", "A new fact the rewrite added", "hooks/reread_check.py:40")
HCS_T_NEW_LINE = hcs_text(extra=(hcs_line(HCS_P8, HCS_NEW),))
HCS_T_NEW_NEVER = hcs_text(extra=(hcs_line(HCS_P8, "never"),))

HCS_HANDOFF = hs_handoff(HCS_CFG, HCS_SID)
HCS_HANDOFF_FULL = hs_handoff(HCS_CFG, HCS_SID_FULL)
HCS_INBOX = hs_inbox(HCS_CFG, HCS_SID)

# One compact_boundary record, as lint/report_guard.py reads it. A copy, not an import: importing the lint suite's test
# module runs its helpers' imports, and its own compact_boundary() is a test helper, not a shared home.
HCS_BOUNDARY = json.dumps({"type": "system", "subtype": "compact_boundary", "isSidechain": False})


def hcs_tool(tool_id, name, tool_input, sidechain=False, agent=False):
    """One tool_use line of the main session. `sidechain` marks it as a sidechain record; `agent` gives it an agent_id."""
    line = json.loads(role_use(tool_id, name, tool_input))
    if sidechain:
        line["isSidechain"] = True
    if agent:
        line["agent_id"] = "agent-7f3c"
    return json.dumps(line)


def hcs_read(tool_id, path, **kw):
    return hcs_tool(tool_id, "Read", {"file_path": HCS_WT + "/" + path}, **kw)


def hcs_handoff_read(tool_id):
    return hcs_tool(tool_id, "Read", {"file_path": HCS_HANDOFF})


def hcs_result(tool_id, error=False, tool_use_result=None):
    """The user line that answers call `tool_id`: an error result when `error`, else a good one. `tool_use_result`, when
    given, is the record's toolUseResult (a failed local SendMessage carries success false there)."""
    line = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": error,
         "content": [{"type": "text", "text": "File does not exist." if error else "ok"}]}]}}
    if tool_use_result is not None:
        line["toolUseResult"] = tool_use_result
    return json.dumps(line)


# The transcript fixtures. "none" is an empty file: readable, with no evidence. "unreadable" is a folder.
HCS_TX_LINES = {
    "none": [],
    "ev_p1": [hcs_read("p1", "hooks/precompact_handoff.py")],
    "ev_p1_p5": [hcs_read("e1", "hooks/precompact_handoff.py"),
                 hcs_tool("e2", "Bash", {"command": "git rev-parse --short HEAD"})],
    "ev_p2_p3": [hcs_read("q1", "docs/decisions/premise-format.md"),
                 hcs_tool("q2", "Bash", {"command": VCS + " show 624dcc188 --stat"})],
    # Reads for P1 and P2 only. The handoff's own Read is in it too, and backs nothing.
    "incident": [hcs_read("i1", "hooks/precompact_handoff.py"), hcs_read("i2", "docs/decisions/premise-format.md"),
                 hcs_handoff_read("i3")],
    "no_boundary": [hcs_read("n1", "hooks/precompact_handoff.py"), hcs_read("n2", "docs/decisions/premise-format.md"),
                    hcs_handoff_read("n3")],
    # Evidence before the last boundary: the second boundary comes after it, so nothing counts.
    "pre_boundary": [hcs_read("b1", "hooks/precompact_handoff.py"), HCS_BOUNDARY, hcs_handoff_read("b2"),
                     HCS_BOUNDARY],
    "post_boundary": [HCS_BOUNDARY, hcs_handoff_read("c1"), hcs_read("c2", "hooks/precompact_handoff.py")],
    "sidechain": [hcs_read("s1", "hooks/precompact_handoff.py", sidechain=True)],
    "agent_id": [hcs_read("a1", "hooks/precompact_handoff.py", agent=True)],
    "other_read": [hcs_read("o1", "hooks/reread_check.py"), hcs_handoff_read("o2")],
    "handoff_read": [hcs_handoff_read("h1")],
    # A Write of the handoff that names P1's token: the earlier rewrite must not back a later restamp of P1.
    "handoff_write": [hcs_tool("w1", "Write", {"file_path": HCS_HANDOFF, "content": HCS_OLD_TEXT})],
    # Full-size: a boundary, 2000 unrelated reads, then the evidence for P1 at the end.
    "long": [HCS_BOUNDARY] + [hcs_read("L%d" % n, "lib/unrelated-%d.md" % n) for n in range(2000)]
            + [hcs_read("lz", "hooks/precompact_handoff.py")],
    # A Write or Edit of another file, or a git commit, that names a Source backs nothing. A read does.
    "write_other": [hcs_tool("x1", "Write", {"file_path": HCS_WT + "/notes.md", "content": "The guard is hooks/guard.py."})],
    "edit_other": [hcs_tool("x2", "Edit", {"file_path": HCS_WT + "/notes.md", "old_string": "TODO",
                                           "new_string": "See hooks/guard.py."})],
    "bash_commit": [hcs_tool("x3", "Bash", {"command": "git -C " + HCS_WT + " commit -m 'Tighten hooks/guard.py'"})],
    "read_guard": [hcs_read("g1", "hooks/guard.py")],
    "grep_guard": [hcs_tool("g2", "Grep", {"pattern": "handoff_stamp_hit", "path": HCS_WT + "/hooks/guard.py"})],
    "glob_guard": [hcs_tool("g3", "Glob", {"pattern": "hooks/guard.py"})],
    "bash_read_guard": [hcs_tool("g4", "Bash", {"command": "grep -n handoff_stamp_hit " + HCS_WT + "/hooks/guard.py"})],
    # A failed call backs nothing, and the same call with a good result does. A failure is an error
    # result, or a toolUseResult that says success false (lint/_transcript.py failed_tool_use_ids reads both).
    "failed_read": [hcs_read("f1", "hooks/precompact_handoff.py"), hcs_result("f1", error=True)],
    "failed_flag": [hcs_read("f2", "hooks/precompact_handoff.py"), hcs_result("f2", tool_use_result={"success": False})],
    "ok_read": [hcs_read("k1", "hooks/precompact_handoff.py"), hcs_result("k1")],
    # A send, or a write-named MCP tool, backs nothing, with the token or without it. A read-named one does.
    "send_token": [hcs_tool("s1", "mcp__claude-code-remote__send_message", {"text": "P1 is in hooks/precompact_handoff.py."})],
    "send_only": [hcs_tool("s2", "mcp__claude-code-remote__send_message", {"text": "Premises checked."})],
    "review_token": [hcs_tool("r1", "mcp__github__pull_request_review_write",
                              {"method": "create", "body": "Read hooks/precompact_handoff.py."})],
    "review_only": [hcs_tool("r2", "mcp__github__pull_request_review_write", {"method": "create", "body": "Looks good."})],
    "resolve_token": [hcs_tool("t1", "mcp__github__resolve_review_thread",
                               {"threadId": "PRRT_1", "note": "hooks/precompact_handoff.py"})],
    "resolve_only": [hcs_tool("t2", "mcp__github__resolve_review_thread", {"threadId": "PRRT_1"})],
    "get_token": [hcs_tool("m1", "mcp__github__get_file_contents",
                           {"owner": "org", "repo": "repo", "path": "hooks/precompact_handoff.py"})],
    "get_only": [hcs_tool("m2", "mcp__github__get_file_contents", {"owner": "org", "repo": "repo", "path": "README.md"})],
}
# Full size: the same last call after 2000 unrelated reads, with an error result and with a good one.
HCS_TX_LINES["long_failed"] = HCS_TX_LINES["long"] + [hcs_result("lz", error=True)]
HCS_TX_LINES["long_ok"] = HCS_TX_LINES["long"] + [hcs_result("lz")]


def hcs_tx(name):
    return os.path.join(HCS_TX, name + ".jsonl")


def write_hcs_transcripts():
    os.makedirs(HCS_TX, exist_ok=True)
    for name, lines in HCS_TX_LINES.items():
        with open(hcs_tx(name), "w", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in lines))
    os.makedirs(hcs_tx("unreadable"), exist_ok=True)   # a folder: the guard's open() fails on it


def _build_hcs_intact():
    hs_install(HCS_CFG, hs_prompt_text())
    write(HCS_HANDOFF, HCS_OLD_TEXT)
    write(HCS_HANDOFF_FULL, HCS_FULL_TEXT)


def _build_hcs_dir():
    os.makedirs(hs_prompt_path(HCS_CFG_DIR), exist_ok=True)   # the prompt path is a directory: unreadable
    write(hs_handoff(HCS_CFG_DIR, HCS_SID), HCS_OLD_TEXT)


lazy_fixture([HCS_CFG], _build_hcs_intact)
lazy_fixture([HCS_CFG_DIR], _build_hcs_dir)
lazy_fixture([hcs_tx(name) for name in HCS_TX_LINES] + [hcs_tx("unreadable")], write_hcs_transcripts)


def hcs_args(tool, tool_input, config=HCS_CFG, session=HCS_SID, transcript=None):
    """The keyword arguments of hcs_decide: one call to `session`'s handoff under `config`."""
    return dict(config=config, tool=tool, tool_input=tool_input, session=session, transcript=transcript)


def hcs_write(text, transcript=None, config=HCS_CFG, session=HCS_SID):
    return hcs_args("Write", {"file_path": hs_handoff(config, session), "content": text}, config, session, transcript)


def hcs_edit(old, new, transcript=None, config=HCS_CFG, session=HCS_SID):
    return hcs_args("Edit", {"file_path": hs_handoff(config, session), "old_string": old, "new_string": new},
                    config, session, transcript)


def hcs_multi(edits, transcript=None, config=HCS_CFG, session=HCS_SID):
    return hcs_args("MultiEdit", {"file_path": hs_handoff(config, session), "edits": edits}, config, session, transcript)


def hcs_decide(config, tool, tool_input, session=HCS_SID, transcript=None):
    case = hs_case(config, tool, tool_input, session)
    case["transcript"] = transcript   # hs_case sets none, so a case names its transcript here or passes None
    return decide(case)


def hcs_twin(label, refused, allowed):
    """`refused` is a call the rule must deny: the same write with no evidence, or with evidence before the last
    boundary. `allowed` is the call the case is about, which must pass silently."""
    def check():
        got = hcs_decide(**refused)
        if got[0] != "deny":
            return False, "%s: the refused call got %r, want a deny by %s" % (label, got[0], HCS_RULE)
        if HCS_RULE not in got[1]:
            return False, "%s: the refused call is denied, but not by %s" % (label, HCS_RULE)
        got = hcs_decide(**allowed)
        if got != ("allow", ""):
            return False, "%s: the allowed call got %r, want a silent allow" % (label, got)
        return True, "%s: refused without evidence, allowed silently with it" % label
    return check


NO_EVIDENCE = hcs_write(HCS_T_P1, transcript=hcs_tx("none"))   # the control most allow cases share

# --- Deny cases: plain add() cases, each one expects the rule to refuse.
# Five premises restamped, evidence for two. It refuses the three unbacked, and names neither of the two.
add("handoff-checked-stamp: five restamped premises, backed for two, are refused, naming the three unbacked and not the two",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("incident"),
    carries=("P3", "P4", "P5", "624dcc188", "hooks/reread_check.py", "git rev-parse --short HEAD"),
    lacks=("P1", "P2", "hooks/precompact_handoff.py", "docs/decisions/premise-format.md"),
    file_path=HCS_HANDOFF, content=HCS_T_INCIDENT)
add("handoff-checked-stamp: a restamp with an empty transcript is refused, naming P1 and its token, and no other premise",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_P1)
add("handoff-checked-stamp: an Edit that restamps P1 with no evidence is refused, naming P1 and its token",
    "deny", HCS_RULE, tool="Edit", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, old_string=hcs_row("P1", HCS_OLD), new_string=hcs_row("P1", HCS_NEW))
add("handoff-checked-stamp: a MultiEdit that restamps P2 and P3 with no evidence is refused, naming both",
    "deny", HCS_RULE, tool="MultiEdit", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P2", "P3", "docs/decisions/premise-format.md", "624dcc188"), lacks=("P1", "P4", "P5"),
    file_path=HCS_HANDOFF,
    edits=[{"old_string": hcs_row("P2", HCS_OLD), "new_string": hcs_row("P2", HCS_NEW)},
           {"old_string": hcs_row("P3", HCS_OLD), "new_string": hcs_row("P3", HCS_NEW)}])
add("handoff-checked-stamp: a new P8 line is a change: dated with no evidence, it is refused, naming P8 and its token",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P8", "hooks/reread_check.py"), lacks=("P1", "P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_NEW_LINE)
add("handoff-checked-stamp: a token-less premise restamped after a read of the handoff alone is refused, naming any read",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("handoff_read"),
    carries=("P7", "any read"), lacks=("P1", "P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P7)
add("handoff-checked-stamp: a token-less premise restamped with an empty transcript is refused, naming any read",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P7", "any read"), lacks=("P1", "P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P7)
add("handoff-checked-stamp: a restamp backed only by an agent's read (isSidechain true) is refused, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("sidechain"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P1)
add("handoff-checked-stamp: a restamp backed only by an agent's read (an agent_id) is refused, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("agent_id"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P1)
add("handoff-checked-stamp: a restamp backed only by a read before the last compact boundary is refused, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("pre_boundary"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P1)
add("handoff-checked-stamp: a restamp backed only by the session's own earlier Write of the handoff is refused, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("handoff_write"),
    carries=("P1", "hooks/precompact_handoff.py"), lacks=("P2", "P3", "P4", "P5"),
    file_path=HCS_HANDOFF, content=HCS_T_P1)
add("handoff-checked-stamp: a token-less premise with a lone quote and comment openers in its Source is refused with no evidence",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P9", "any read"), lacks=("P1", "P2", "P3", "P4", "P5", "P7"),
    file_path=HCS_HANDOFF, content=HCS_T_P9)
add("handoff-checked-stamp: a full-size handoff with one unbacked restamp is refused, naming that premise only",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID_FULL, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P12", "any read"), lacks=("P10", "P11", "P13", "P14", "P15", "P16", "P9", "P7"),
    file_path=HCS_HANDOFF_FULL, content=HCS_T_FULL_P12)


# --- Allow cases: each one is a twin. A deny control comes first; the allowed call must then pass silently.
def hcs_cost_check():
    """Each restamp the rule refuses writes its guard.log line only and reads the transcript once. A restamp it allows,
    with evidence, writes no file, starts no process and reads the transcript at most once. A write that restamps nothing
    reads no transcript. The refusal is the control: a probe that counted nothing would show zero writes too."""
    refused = hs_probe(HCS_CFG, "Write", {"file_path": HCS_HANDOFF, "content": HCS_T_P1},
                       session=HCS_SID, transcript=hcs_tx("none"))
    if refused[2] is None:
        return False, "the probe printed no count for the refused restamp"
    if refused[0] != "deny" or HCS_RULE not in refused[1]:
        return False, "control: the restamp with no evidence got %r, want a deny by %s" % (refused[0], HCS_RULE)
    if refused[2] != ["guard.log"] or refused[3]:
        return False, "the refused restamp wrote %r and started %r, want one guard.log write and no start" % (
            refused[2], refused[3])
    if len(refused[4]) != 1:
        return False, "the refused restamp read the transcript %d times, want exactly one" % len(refused[4])
    allowed = hs_probe(HCS_CFG, "Write", {"file_path": HCS_HANDOFF, "content": HCS_T_P1},
                       session=HCS_SID, transcript=hcs_tx("ev_p1"))
    if allowed[2] is None:
        return False, "the probe printed no count for the allowed restamp"
    if allowed[0] != "allow" or allowed[1]:
        return False, "the allowed restamp got %r, want a silent allow" % (allowed[0],)
    if allowed[2] or allowed[3]:
        return False, "the allowed restamp wrote %r and started %r, want none" % (allowed[2], allowed[3])
    if len(allowed[4]) > 1:
        return False, "the allowed restamp read the transcript %d times, want at most once" % len(allowed[4])
    same = hs_probe(HCS_CFG, "Write", {"file_path": HCS_HANDOFF, "content": HCS_OLD_TEXT},
                    session=HCS_SID, transcript=hcs_tx("none"))
    if same[2] is None:
        return False, "the probe printed no count for an unchanged write"
    if same[0] != "allow" or same[1]:
        return False, "an unchanged write got %r, want a silent allow" % (same[0],)
    if same[2] or same[3]:
        return False, "an unchanged write wrote %r and started %r, want none" % (same[2], same[3])
    if same[4]:
        return False, "an unchanged write read the transcript %d times, want none" % len(same[4])
    return True, "a restamp with evidence writes no file and starts no process; a refusal writes its guard.log line and reads the transcript once; an unchanged write reads no transcript"


def hcs_scope_check():
    """The incident transcript backs P1 and P2 and holds no token of P3, P4 or P5. The handoff on disk holds the old stamps,
    once each for the Edit and MultiEdit cases' old text, and the full-size handoff holds 15 premises. The cases judge these,
    so they must hold first."""
    materialize(HCS_CFG)
    materialize(hcs_tx("incident"))
    with open(hcs_tx("incident"), "r", encoding="utf-8") as handle:
        transcript = handle.read()
    for token in ("hooks/precompact_handoff.py", "docs/decisions/premise-format.md"):
        if token not in transcript:
            return False, "the incident transcript lacks %s, which backs a premise" % token
    for token in ("624dcc188", "hooks/reread_check.py", "git rev-parse --short HEAD"):
        if token in transcript:
            return False, "the incident transcript holds %s, which must stay unbacked" % token
    with open(HCS_HANDOFF, "r", encoding="utf-8") as handle:
        disk = handle.read()
    if disk != HCS_OLD_TEXT:
        return False, "the handoff on disk is not the handoff with every stamp old"
    for pid in ("P1", "P2", "P3"):
        if disk.count(hcs_row(pid, HCS_OLD)) != 1:
            return False, "the handoff on disk holds the %s line %d times, want once" % (pid, disk.count(hcs_row(pid, HCS_OLD)))
    with open(HCS_HANDOFF_FULL, "r", encoding="utf-8") as handle:
        full = handle.read()
    if len(re.findall(r"^- P\d+ \[", full, re.M)) != 15:
        return False, "the full-size handoff does not hold 15 premise lines"
    return True, "the incident transcript backs P1 and P2 only; the handoff on disk holds the old stamps; the full-size handoff holds 15 premises"


LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: scope: the incident transcript backs P1 and P2 only, and the handoff on disk "
                         "holds the old stamps", hcs_scope_check))

# Case 2: a restamp backed by a Read (a path) and a Bash call (a backticked command, and a commit hash in another).
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a restamp backed by a Read and by a Bash call passes silently",
                         hcs_twin("evidence by a Read and a Bash call",
                                  refused=hcs_write(HCS_T_P1_P5, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_P1_P5, transcript=hcs_tx("ev_p1_p5")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Bash call that names a commit hash backs a restamp, passes silently",
                         hcs_twin("evidence by a Bash call that names a commit",
                                  refused=hcs_write(HCS_T_P2_P3, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_P2_P3, transcript=hcs_tx("ev_p2_p3")))))
# Case 3: an unchanged stamp passes, and a reworded statement under the same stamp passes.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a write with every stamp unchanged passes silently",
                         hcs_twin("unchanged stamps",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_OLD_TEXT, transcript=hcs_tx("none")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a rewording that keeps every stamp passes silently",
                         hcs_twin("a reworded statement",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_REWORD, transcript=hcs_tx("none")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a full-size handoff with every stamp unchanged passes silently",
                         hcs_twin("a full-size handoff, unchanged",
                                  refused=hcs_write(HCS_T_FULL_P12, transcript=hcs_tx("none"), session=HCS_SID_FULL),
                                  allowed=hcs_write(HCS_FULL_TEXT, transcript=hcs_tx("none"), session=HCS_SID_FULL))))
# Case 4: Checked never passes without evidence.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a restamp to Checked never passes silently with no evidence",
                         hcs_twin("Checked never",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_NEVER_P1, transcript=hcs_tx("none")))))
# Case 5: a ruling premise is restamped without evidence.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a restamp of a ruling premise passes silently with no evidence",
                         hcs_twin("a ruling premise",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P6, transcript=hcs_tx("none")))))
# Case 6: no compact boundary: the whole transcript counts. The full-size transcript holds the evidence at its end.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: with no compact boundary, the whole transcript counts",
                         hcs_twin("no compact boundary",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1_P2, transcript=hcs_tx("no_boundary")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: with no compact boundary, a 2000-read transcript counts its last read",
                         hcs_twin("a full-size transcript",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("long")))))
# Case 7: evidence after the last boundary counts; evidence before it does not (add() case above).
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a read after the last compact boundary backs a restamp, passes silently",
                         hcs_twin("evidence after the last boundary",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("pre_boundary")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("post_boundary")))))
# Case 10: one unrelated read backs a token-less premise.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: one non-handoff read backs a token-less premise, passes silently",
                         hcs_twin("one unrelated read",
                                  refused=hcs_write(HCS_T_P7, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_P7, transcript=hcs_tx("other_read")))))
# Case 9's control: the handoff Read backs nothing, while another read does (the add() case above holds the refusal).
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a non-handoff read backs a token-less premise where the handoff's Read does not",
                         hcs_twin("a read of another file",
                                  refused=hcs_write(HCS_T_P7, transcript=hcs_tx("handoff_read")),
                                  allowed=hcs_write(HCS_T_P7, transcript=hcs_tx("other_read")))))
# Case 11: fail open. Each subject is a case the rule allows silently; the control is the same restamp with an empty
# transcript and the intact prompt.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: fail open when the payload names no transcript",
                         hcs_twin("no transcript_path", refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1, transcript=None))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: fail open when the transcript file is missing",
                         hcs_twin("a missing transcript", refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("absent")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: fail open when the transcript is unreadable",
                         hcs_twin("an unreadable transcript", refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("unreadable")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: fail open when the installed prompt cannot be read",
                         hcs_twin("an unreadable prompt", refused=NO_EVIDENCE,
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("none"), config=HCS_CFG_DIR))))
# Case 12: a new line dated with no evidence is refused (add() above); with Checked never, it passes.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a new P8 line with Checked never passes silently",
                         hcs_twin("a new line, Checked never",
                                  refused=hcs_write(HCS_T_NEW_LINE, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_NEW_NEVER, transcript=hcs_tx("none")))))
# Case 13: Edit and MultiEdit with evidence pass; the same edits with no evidence are refused (add() cases above).
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: an Edit backed by a Read passes silently",
                         hcs_twin("an Edit with evidence",
                                  refused=hcs_edit(hcs_row("P1", HCS_OLD), hcs_row("P1", HCS_NEW), transcript=hcs_tx("none")),
                                  allowed=hcs_edit(hcs_row("P1", HCS_OLD), hcs_row("P1", HCS_NEW), transcript=hcs_tx("ev_p1")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a MultiEdit backed by a Read and a Bash call passes silently",
                         hcs_twin("a MultiEdit with evidence",
                                  refused=hcs_multi([{"old_string": hcs_row("P2", HCS_OLD), "new_string": hcs_row("P2", HCS_NEW)},
                                                     {"old_string": hcs_row("P3", HCS_OLD), "new_string": hcs_row("P3", HCS_NEW)}],
                                                    transcript=hcs_tx("none")),
                                  allowed=hcs_multi([{"old_string": hcs_row("P2", HCS_OLD), "new_string": hcs_row("P2", HCS_NEW)},
                                                     {"old_string": hcs_row("P3", HCS_OLD), "new_string": hcs_row("P3", HCS_NEW)}],
                                                    transcript=hcs_tx("ev_p2_p3")))))
# Case 14: a repo's HANDOFF.md and an inbox beside the handoff are not session handoffs, and pass.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a repo's own HANDOFF.md, restamped with no evidence, passes silently",
                         hcs_twin("a repo HANDOFF.md",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_args("Write", {"file_path": os.path.join(NOGIT, "HANDOFF.md"),
                                                             "content": HCS_T_P1}, transcript=hcs_tx("none")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: the owner-feedback inbox, restamped with no evidence, passes silently",
                         hcs_twin("the owner-feedback inbox",
                                  refused=NO_EVIDENCE,
                                  allowed=hcs_args("Write", {"file_path": HCS_INBOX,
                                                             "content": hcs_line(("P1", "read",
                                                                                  "The guard judges each handoff write",
                                                                                  "hooks/precompact_handoff.py:279"),
                                                                                 HCS_NEW) + "\n"},
                                                   transcript=hcs_tx("none")))))
# Scanner text: a lone quote and comment openers in a Source. The rule reads markdown lines, and this case holds one.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a token-less Source with a quote and comment openers is judged, and one read backs it",
                         hcs_twin("a Source with a quote and comment openers",
                                  refused=hcs_write(HCS_T_P9, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_P9, transcript=hcs_tx("other_read")))))
# The cost check, last: its refusal and its allow each read the transcript once.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: an allowed restamp writes no file and starts no process; a refusal writes its "
                         "guard.log line and reads the transcript once; an unchanged write reads no transcript", hcs_cost_check))


# --- Cases for stamps spelled `Checked:` or `Re-checked`, a stamp that is absent or empty, a new premise line,
# and a premise whose kind changes in the write. A control keeps the rule from refusing a restamp it allows.
HCS_SID_COLON = "4b8e1d62-0000-4000-8000-00000000c0a2"    # a handoff whose stamps are spelled `Checked: <value>`
HCS_COLON = hs_handoff(HCS_CFG, HCS_SID_COLON)
HCS_GUARD = ("P8", "read", "The guard refuses a restamp with no evidence", "hooks/guard.py:1176")
HCS_T_GUARD = hcs_text(extra=(hcs_line(HCS_GUARD, HCS_NEW),))   # a new dated line whose Source names hooks/guard.py
HCS_RELABEL_ROWS = tuple((pid, "ruling" if pid == "P1" else kind, statement, source)
                         for pid, kind, statement, source in HCS_ROWS)
HCS_DEMOTE_ROWS = tuple((pid, "read" if pid == "P6" else kind, statement, source)
                        for pid, kind, statement, source in HCS_ROWS)
HCS_T_RELABEL = hcs_text(rows=HCS_RELABEL_ROWS, new=("P1",))   # P1 was [read]; the write makes it [ruling] and restamps it
HCS_T_DEMOTE = hcs_text(rows=HCS_DEMOTE_ROWS, new=("P6",))     # P6 was [ruling]; the write makes it [read] and restamps it


def hcs_stamped(row, stamp):
    """The premise line of `row` with `stamp` after its Source (the stamp's own period included), or none when `stamp`
    is ""."""
    pid, kind, statement, source = row
    head = "- %s [%s] %s. Source: %s." % (pid, kind, statement, source)
    return head + " " + stamp if stamp else head


def hcs_p1_text(p1_stamp):
    """A handoff whose P1 line ends in `p1_stamp`, with every other premise at the old stamp."""
    return hs_text(premises=[hcs_stamped(row, p1_stamp) if row[0] == "P1" else hcs_line(row, HCS_OLD)
                             for row in HCS_ROWS])


HCS_T_SPELL_COLON = hcs_p1_text("Checked: %s." % HCS_NEW)
HCS_T_SPELL_RE = hcs_p1_text("Re-checked %s." % HCS_NEW)
HCS_T_ABSENT = hcs_p1_text("")                  # P1 loses its stamp
HCS_T_EMPTY = hcs_p1_text("Checked .")          # P1's stamp has no value


def hcs_colon_text(p1_value):
    """A handoff whose every stamp is spelled `Checked: <value>`: P1 at `p1_value`, the rest at the old value."""
    return hs_text(premises=[hcs_stamped(row, "Checked: %s." % (p1_value if row[0] == "P1" else HCS_OLD))
                             for row in HCS_ROWS])


HCS_COLON_OLD = hcs_colon_text(HCS_OLD)     # the handoff on disk for the colon session
HCS_T_COLON_NEW = hcs_colon_text(HCS_NEW)   # the same, with P1 restamped in the same spelling


def _build_hcs_colon():
    write(HCS_COLON, HCS_COLON_OLD)


lazy_fixture([HCS_COLON], _build_hcs_colon)


def hcs_colon_scope():
    """The colon handoff on disk is the handoff with every stamp spelled Checked: at the old value, so the twin's
    refused write changes P1 alone. The twin branches on that spelling, so it asserts the fixture first (P7)."""
    materialize(HCS_COLON)
    with open(HCS_COLON, "r", encoding="utf-8") as handle:
        disk = handle.read()
    if disk != HCS_COLON_OLD:
        return False, "the colon handoff on disk is not the handoff with every stamp spelled Checked: at the old value"
    return True, "the colon handoff on disk holds every stamp spelled Checked: at the old value"


def hcs_scoped(scope, twin):
    """`twin`, run only once `scope` holds: a scope failure is the case's failure, named as the scope."""
    def check():
        ok, note = scope()
        if not ok:
            return False, note
        return twin()
    return check


# Case 1: a stamp spelled other than `Checked <value>` counts. A new value under another spelling, or a stamp that is
# absent or has no value after the write, is a change, and it is refused with no evidence.
add("handoff-checked-stamp: a stamp spelled Checked: with a new value is refused with no evidence, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1",), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_SPELL_COLON)
add("handoff-checked-stamp: a stamp spelled Re-checked with a new value is refused with no evidence, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1",), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_SPELL_RE)
add("handoff-checked-stamp: a stamp present before and absent after is refused with no evidence, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1",), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_ABSENT)
add("handoff-checked-stamp: a stamp present before with no value after is refused with no evidence, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1",), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_EMPTY)
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a stamp spelled Checked: with its value unchanged passes silently; with a new "
                         "value it is refused with no evidence",
                         hcs_scoped(hcs_colon_scope,
                                    hcs_twin("a stamp spelled Checked:",
                                             refused=hcs_write(HCS_T_COLON_NEW, transcript=hcs_tx("none"),
                                                               session=HCS_SID_COLON),
                                             allowed=hcs_write(HCS_COLON_OLD, transcript=hcs_tx("none"),
                                                               session=HCS_SID_COLON)))))

# Case 2: a Source's token backed only by a Write or Edit of another file, or by a non-read Bash call, backs nothing. The
# controls: a Read, a Grep, a Glob and a Bash read of the token each back it.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Write of another file that names a token-bearing Source backs no restamp; "
                         "a Read of that Source does",
                         hcs_twin("a Write of another file",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("write_other")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("read_guard")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: an Edit of another file that names a token-bearing Source backs no restamp; "
                         "a Read of that Source does",
                         hcs_twin("an Edit of another file",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("edit_other")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("read_guard")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a git commit that names a token-bearing Source backs no restamp; "
                         "a Read of that Source does",
                         hcs_twin("a git commit",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("bash_commit")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("read_guard")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Grep of a token-bearing Source backs a restamp, passes silently",
                         hcs_twin("a Grep",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("grep_guard")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Glob of a token-bearing Source backs a restamp, passes silently",
                         hcs_twin("a Glob",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("glob_guard")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Bash read of a token-bearing Source backs a restamp, passes silently",
                         hcs_twin("a Bash read",
                                  refused=hcs_write(HCS_T_GUARD, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_GUARD, transcript=hcs_tx("bash_read_guard")))))

# Case 3: a failed call backs nothing; the same call with a good result backs the premise. The full-size pair ends with
# that call after 2000 unrelated reads.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a failed Read backs no restamp; the same Read with a good result does, "
                         "passes silently",
                         hcs_twin("a failed Read",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("failed_read")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("ok_read")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a Read whose toolUseResult says success false backs no restamp; the same "
                         "Read with a good result does, passes silently",
                         hcs_twin("a Read with success false",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("failed_flag")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("ok_read")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a failed Read after 2000 unrelated reads backs no restamp; the same Read "
                         "with a good result does, passes silently",
                         hcs_twin("a failed Read at full size",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("long_failed")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("long_ok")))))

# Case 4: a send, and a write-named MCP tool, back nothing, with the token in their text or with a token-less Source. A
# read-named MCP tool backs the token it holds, and a token-less Source.
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a send_message whose text holds the Source backs no restamp; a Read of the "
                         "Source does",
                         hcs_twin("a send_message with the token",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("send_token")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("ok_read")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a send_message that is the only call for a token-less Source backs nothing; a "
                         "read-named MCP tool does",
                         hcs_twin("a send_message alone",
                                  refused=hcs_write(HCS_T_P7, transcript=hcs_tx("send_only")),
                                  allowed=hcs_write(HCS_T_P7, transcript=hcs_tx("get_only")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a pull_request_review_write whose input holds the Source backs no restamp; a "
                         "Read of the Source does",
                         hcs_twin("a review write with the token",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("review_token")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("ok_read")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a pull_request_review_write that is the only call for a token-less Source backs "
                         "nothing; a read-named MCP tool does",
                         hcs_twin("a review write alone",
                                  refused=hcs_write(HCS_T_P7, transcript=hcs_tx("review_only")),
                                  allowed=hcs_write(HCS_T_P7, transcript=hcs_tx("get_only")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a resolve_review_thread whose input holds the Source backs no restamp; a Read of "
                         "the Source does",
                         hcs_twin("a thread resolve with the token",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("resolve_token")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("ok_read")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a resolve_review_thread that is the only call for a token-less Source backs "
                         "nothing; a read-named MCP tool does",
                         hcs_twin("a thread resolve alone",
                                  refused=hcs_write(HCS_T_P7, transcript=hcs_tx("resolve_only")),
                                  allowed=hcs_write(HCS_T_P7, transcript=hcs_tx("get_only")))))
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a read-named MCP tool whose input holds the Source backs a restamp, passes "
                         "silently",
                         hcs_twin("a read-named MCP tool with the token",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_P1, transcript=hcs_tx("get_token")))))

# Note 6: the kind that judges a premise is its BEFORE kind. A premise relabelled to [ruling] with no evidence is refused;
# a premise that was [ruling] before passes, even when the write relabels it.
add("handoff-checked-stamp: a premise relabelled [ruling] in the same write, restamped with no evidence, is refused by its "
    "before kind, naming P1",
    "deny", HCS_RULE, tool="Write", cwd=NOGIT, session=HCS_SID, config=HCS_CFG, transcript=hcs_tx("none"),
    carries=("P1",), lacks=("P2", "P3", "P4", "P5", "P7", "P9"),
    file_path=HCS_HANDOFF, content=HCS_T_RELABEL)
LOG_CHECKS_EXTRA.append(("handoff-checked-stamp: a premise that was [ruling] before and is relabelled [read] in the same write, "
                         "restamped with no evidence, passes silently",
                         hcs_twin("a ruling premise relabelled to read",
                                  refused=hcs_write(HCS_T_P1, transcript=hcs_tx("none")),
                                  allowed=hcs_write(HCS_T_DEMOTE, transcript=hcs_tx("none")))))


# =========================================================================== the machine-load brake
# The brake's local cases are local runs. A cloud container sets CLAUDE_CODE_REMOTE=true, which turns the brake off, so the
# suite drops it here, and a cloud case passes its own value to lb_decision_check (`remote`). No other case reads it.
os.environ.pop("CLAUDE_CODE_REMOTE", None)
