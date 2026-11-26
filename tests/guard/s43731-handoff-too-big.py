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
    # Bytes, not text mode: Windows text mode writes CRLF, which grows the file past HTB_DISK, so a same-size
    # Write would read as a shrink and pass.
    os.makedirs(os.path.dirname(HTB_HANDOFF), exist_ok=True)
    with open(HTB_HANDOFF, "wb") as handle:
        handle.write(htb_text(HTB_DISK).encode("utf-8"))


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


# ------------------------------------------------------------------------ Bash writes past the size limit
# The Bash forms of the Write cases above. Each call puts over-limit text on HTB_NEW's handoff, which has no file on disk, so
# the size of the content is the whole test; the `>>` case grows a handoff that is on disk. The scratch files keep all six
# sections, since the sections rule is judged first. The ~ and $HOME forms run with HOME set to ROOT (hbw_home_expands).
HTB_SCRATCH = os.path.join(ROOT, "htb-scratch")
HTB_OVER_FILE = os.path.join(HTB_SCRATCH, "over.md")      # htb_text(35001): 10001 estimated tokens, six sections
HTB_AT_FILE = os.path.join(HTB_SCRATCH, "at.md")          # htb_text(35000): the limit itself, which passes
HBA_CFG = os.path.join(ROOT, "hba-cfg")                   # an installed prompt, and HTB_NEW's handoff at 35000 bytes
HTB_HOME_REL = os.path.relpath(HTB_NEW_HANDOFF, ROOT).replace(os.sep, "/")
HTB_TILDE = "~/" + HTB_HOME_REL
HTB_DOLLAR = "$HOME/" + HTB_HOME_REL
HTB_HOME = {"HOME": ROOT}


def _build_htb_scratch():
    write(HTB_OVER_FILE, htb_text(35001))
    write(HTB_AT_FILE, htb_text(35000))


def _build_hba():
    hs_install(HBA_CFG, hs_prompt_text())
    write(hs_handoff(HBA_CFG, HTB_NEW), htb_text(35000))


lazy_fixture([HTB_OVER_FILE, HTB_AT_FILE], _build_htb_scratch)
lazy_fixture([HBA_CFG], _build_hba)


def htb_bash_scope():
    """The Bash cases copy scratch files of 35001 and 35000 bytes, and read the ~ and $HOME forms as HTB_NEW's handoff under
    HOME. A file of another size would move the boundary with no other check failing."""
    materialize(HTB_OVER_FILE)
    sizes = (os.path.getsize(HTB_OVER_FILE), os.path.getsize(HTB_AT_FILE))
    if sizes != (35001, 35000):
        return False, "the scratch files are %r bytes, want (35001, 35000)" % (sizes,)
    ok, tilde, dollar = hbw_home_expands(HTB_HOME_REL, hs_handoff(HTB_CFG, HTB_NEW))
    if not ok:
        return False, "with HOME at the fixture root, ~ names %s and $HOME names %s" % (tilde, dollar)
    return True, "the scratch files are 35001 and 35000 bytes, and ~ and $HOME name the new session's handoff"


HTB_BASH_SCOPE_LABEL = ("handoff-too-big: scope: the Bash scratch files are 35001 and 35000 bytes, and ~ and $HOME name "
                        "the new session's handoff")
LOG_FAMILY[HTB_BASH_SCOPE_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((HTB_BASH_SCOPE_LABEL, htb_bash_scope),)


def htb_bash_refuse(name, command, **kw):
    """One Bash call the size rule refuses for HTB_NEW's handoff: the deny, and the estimate of 10001 tokens."""
    sh(name, command, "deny", HTB_RULE, cwd=NOGIT, session=HTB_NEW, config=HTB_CFG,
       carries=("estimated 10001 tokens", "over the limit of 10000"), **kw)


htb_bash_refuse("handoff-too-big: a Bash cp of a scratch file one byte over the limit onto a session handoff is refused, "
              "naming the estimate",
              "cp %s %s" % (HTB_OVER_FILE, HTB_NEW_HANDOFF))
htb_bash_refuse("handoff-too-big: a Bash mv of a scratch file one byte over the limit onto a session handoff is refused, "
              "naming the estimate",
              "mv %s %s" % (HTB_OVER_FILE, HTB_NEW_HANDOFF))
htb_bash_refuse("handoff-too-big: a Bash cat of a scratch file one byte over the limit redirected onto a session handoff is "
              "refused, naming the estimate",
              "cat %s > %s" % (HTB_OVER_FILE, HTB_NEW_HANDOFF))
htb_bash_refuse("handoff-too-big: a heredoc redirected with > one byte over the limit onto a session handoff is refused, "
              "naming the estimate",
              "cat > %s <<'EOF'\n%sEOF\n" % (HTB_NEW_HANDOFF, htb_text(35001)))
htb_bash_refuse("handoff-too-big: a tee of a heredoc one byte over the limit onto a session handoff is refused, naming the "
              "estimate",
              "tee %s <<'EOF'\n%sEOF\n" % (HTB_NEW_HANDOFF, htb_text(35001)))
htb_bash_refuse("handoff-too-big: a python3 -c that writes a literal one byte over the limit onto a session handoff is "
              "refused, naming the estimate",
              "python3 -c \"open('%s', 'w').write('''%s''')\"" % (HTB_NEW_HANDOFF, htb_text(35001)))
htb_bash_refuse("handoff-too-big: a Bash cp of a scratch file one byte over the limit, written with ~, is refused, naming "
              "the estimate",
              "cp %s %s" % (HTB_OVER_FILE, HTB_TILDE), env=HTB_HOME)
htb_bash_refuse("handoff-too-big: a Bash cp of a scratch file one byte over the limit, written with $HOME, is refused, "
              "naming the estimate",
              "cp %s %s" % (HTB_OVER_FILE, HTB_DOLLAR), env=HTB_HOME)
sh("handoff-too-big: a Bash append of one line onto a handoff on disk at 35000 bytes, which goes over, is refused, naming "
   "10007 tokens",
   "cat >> %s <<'EOF'\n%sEOF\n" % (hs_handoff(HBA_CFG, HTB_NEW), HTB_LINE), "deny", HTB_RULE,
   cwd=NOGIT, session=HTB_NEW, config=HBA_CFG, carries=("estimated 10007 tokens", "over the limit of 10000"))

# The controls: the same shapes at the limit, and an append onto a small handoff, pass silently.
sh("handoff-too-big: a Bash cp of a scratch file at the limit, 35000 bytes, onto a session handoff passes, silently",
   "cp %s %s" % (HTB_AT_FILE, HTB_NEW_HANDOFF), "allow", cwd=NOGIT, session=HTB_NEW, config=HTB_CFG, silent=True)
sh("handoff-too-big: a heredoc redirected with > at the limit, 35000 bytes, onto a session handoff passes, silently",
   "cat > %s <<'EOF'\n%sEOF\n" % (HTB_NEW_HANDOFF, htb_text(35000)), "allow",
   cwd=NOGIT, session=HTB_NEW, config=HTB_CFG, silent=True)
sh("handoff-too-big: a Bash append of one line onto a small session handoff on disk passes, silently",
   "cat >> %s <<'EOF'\n%sEOF\n" % (hs_handoff(HS_CFG), HTB_LINE), "allow",
   cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True)
