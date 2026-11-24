# section 43731
# The handoff size limit (decision precompact-handoff, 10000 estimated tokens, set 19:07 CST Nov 23, 2026). A write
# that leaves a session handoff over the limit is refused by handoff-too-big. The estimate is ceil(UTF-8 bytes / 3.5), so
# 35000 bytes is the last size that passes. The fixtures keep all six sections, so handoff-sections allows them and only
# the size is judged.
FAMILY = "handoff-too-big"
HTB_RULE = "handoff-too-big"
HTB_CFG = os.path.join(ROOT, "htb-cfg")              # the installed prompt, and HS_SID's handoff over the limit on disk
HTB_NEW = "5d2a7c10-0000-4000-8000-00000000b16e"     # a session with no handoff on disk
HTB_LINE = "A line of state, kept.\n"                # 23 bytes: the padding is whole lines of it, then blank lines
HTB_BASE = "Nothing in flight.\n"                    # the Work in flight line the Edit and MultiEdit cases grow
HTB_DISK = 36000                                     # the handoff on disk: 10286 estimated tokens, over the limit


def htb_est(nbytes):
    """ceil(bytes / 3.5), in whole numbers: the estimate the rule reads, written here so the fixture sizes are checked."""
    return -(-2 * nbytes // 7)


def htb_text(total):
    """The six-section handoff padded to `total` UTF-8 bytes: whole HTB_LINE lines and then blank lines, after the
    Where things stand body."""
    extra = total - len(hs_text().encode("utf-8"))
    body = HS_BODIES["Where things stand"]
    pad = HTB_LINE * (extra // len(HTB_LINE)) + "\n" * (extra % len(HTB_LINE))
    return hs_text().replace(body, body + pad, 1)


HTB_HANDOFF = hs_handoff(HTB_CFG)                    # HS_SID's handoff: over the limit on disk
HTB_NEW_HANDOFF = hs_handoff(HTB_CFG, HTB_NEW)       # no file on disk


def _build_htb():
    hs_install(HTB_CFG, hs_prompt_text())
    write(HTB_HANDOFF, htb_text(HTB_DISK))


lazy_fixture([HTB_CFG], _build_htb)


def htb_scope():
    """The fixtures are the sizes the cases name, and the handoff on disk is the 36000-byte one that the Edit and
    MultiEdit cases grow. A padding off by a byte would move a boundary claim with no other check failing."""
    for size, tokens in ((35000, 10000), (35001, 10001), (35500, 10143), (36000, 10286), (36500, 10429)):
        got = len(htb_text(size).encode("utf-8"))
        if got != size:
            return False, "htb_text(%d) is %d bytes" % (size, got)
        if htb_est(size) != tokens:
            return False, "%d bytes estimate %d tokens, want %d" % (size, htb_est(size), tokens)
    materialize(HTB_CFG)
    with open(HTB_HANDOFF, "rb") as handle:
        disk = handle.read()
    if disk != htb_text(HTB_DISK).encode("utf-8"):
        return False, "the handoff on disk is not the %d-byte fixture" % HTB_DISK
    if HTB_BASE.encode("utf-8") not in disk:
        return False, "the handoff on disk lacks the Work in flight line the Edit cases grow"
    return True, "the fixtures are 35000, 35001, 35500, 36000 and 36500 bytes, and the disk handoff is 36000 bytes"


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so this section's log check joins LOG_CHECKS directly.
HTB_SCOPE_LABEL = "handoff-too-big: scope: the fixture sizes are the ones the cases name"
LOG_FAMILY[HTB_SCOPE_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((HTB_SCOPE_LABEL, htb_scope),)

add("handoff-too-big: a Write one byte over the limit is refused, naming the estimate and the limit",
    "deny", HTB_RULE, tool="Write", cwd=NOGIT, session=HTB_NEW, config=HTB_CFG,
    carries=("estimated 10001 tokens", "over the limit of 10000"),
    file_path=HTB_NEW_HANDOFF, content=htb_text(35001))
add("handoff-too-big: a Write at the limit, 35000 bytes, passes silently",
    "allow", tool="Write", cwd=NOGIT, session=HTB_NEW, config=HTB_CFG, silent=True,
    file_path=HTB_NEW_HANDOFF, content=htb_text(35000))
add("handoff-too-big: a Write of the size of an over-limit handoff on disk is refused, naming 10286 tokens",
    "deny", HTB_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HTB_CFG,
    carries=("estimated 10286 tokens", "over the limit of 10000"),
    file_path=HTB_HANDOFF, content=htb_text(HTB_DISK))
add("handoff-too-big: a Write that grows an over-limit handoff on disk is refused, naming 10429 tokens",
    "deny", HTB_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HTB_CFG,
    carries=("estimated 10429 tokens", "over the limit of 10000"),
    file_path=HTB_HANDOFF, content=htb_text(36500))
add("handoff-too-big: a Write that shrinks an over-limit handoff on disk passes silently, though the result is still over",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HTB_CFG, silent=True,
    file_path=HTB_HANDOFF, content=htb_text(35500))
add("handoff-too-big: an Edit that cuts a line from an over-limit handoff on disk passes silently",
    "allow", tool="Edit", cwd=NOGIT, session=HS_SID, config=HTB_CFG, silent=True,
    file_path=HTB_HANDOFF, old_string=HTB_LINE, new_string="")
add("handoff-too-big: an Edit that grows an over-limit handoff on disk by one byte is refused, naming 10286 tokens",
    "deny", HTB_RULE, tool="Edit", cwd=NOGIT, session=HS_SID, config=HTB_CFG,
    carries=("estimated 10286 tokens", "over the limit of 10000"),
    file_path=HTB_HANDOFF, old_string=HTB_BASE, new_string=HTB_BASE + "\n")
add("handoff-too-big: a MultiEdit that grows an over-limit handoff on disk is refused, naming 10293 tokens",
    "deny", HTB_RULE, tool="MultiEdit", cwd=NOGIT, session=HS_SID, config=HTB_CFG,
    carries=("estimated 10293 tokens", "over the limit of 10000"),
    file_path=HTB_HANDOFF,
    edits=[{"old_string": HTB_BASE, "new_string": "Nothing in flight; the red run is recorded.\n"}])
