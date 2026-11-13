# section 8728
FAMILY = "push-delete"

# Rule archive-push-gates-delete. A delete of a remote branch that follows an archive push of that branch runs
# only when `&&` joins them, so the push's own exit status gates it. A `;`, a newline, `||`, or a pipe on the push
# hides or breaks that status, so each is refused. A source of `HEAD`, `origin/<name>` or `<name>` is the branch
# `<name>`, `${b}` and `$b` are one name, and a taken archive name `archive/<name>-N` is the branch `<name>`.
ARCHIVE_GATE_RULE = "archive-push-gates-delete"
ARCHIVE_GATE_REMEDY = "&&"
ARCHIVE_GATE_PUSH = VCS + " push origin HEAD:archive/feat"
ARCHIVE_GATE_REF_PUSH = VCS + " push origin feat:refs/heads/archive/feat"
ARCHIVE_GATE_DELETE = VCS + " push --delete origin feat"
ARCHIVE_GATE_COLON_DELETE = VCS + " push origin :feat"


def archive_gate_refused(name, command):
    """One refusal: the delete after the archive push is not gated by `&&`, so the deny names the rule and `&&`."""
    sh("push: " + name, command, "deny", ARCHIVE_GATE_RULE, cwd=PUSHFEAT, carries=ARCHIVE_GATE_REMEDY)


def archive_gate_allowed(name, command):
    """One control: an allow that must print nothing."""
    sh("push: " + name, command, "allow", cwd=PUSHFEAT, silent=True)


archive_gate_refused("archive push, then --delete joined by ; is refused",
                     ARCHIVE_GATE_PUSH + "; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, then :feat joined by ; is refused",
                     ARCHIVE_GATE_PUSH + "; " + ARCHIVE_GATE_COLON_DELETE)
archive_gate_refused("archive push piped to tail, then --delete joined by ; is refused",
                     ARCHIVE_GATE_PUSH + " | tail; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push piped to tail, then --delete joined by && is refused: && gates tail's status",
                     ARCHIVE_GATE_PUSH + " | tail && " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, then --delete joined by || is refused",
                     ARCHIVE_GATE_PUSH + " || " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push on one line, --delete on the next line is refused",
                     ARCHIVE_GATE_REF_PUSH + "\n" + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, &&, echo, then --delete joined by ; is refused: the ; after the gate counts",
                     ARCHIVE_GATE_PUSH + " && echo done; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, echo, then --delete joined by && is refused: the ; before the echo counts",
                     ARCHIVE_GATE_PUSH + "; echo done && " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, a quoted apostrophe, then --delete is refused",
                     ARCHIVE_GATE_PUSH + '; echo "don\'t"; ' + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, a quoted hash, then --delete is refused",
                     ARCHIVE_GATE_PUSH + '; echo "# x"; ' + ARCHIVE_GATE_DELETE)
archive_gate_refused("loop body: archive push piped to tail, then --delete joined by ; is refused",
                     "for _ in 1; do " + ARCHIVE_GATE_PUSH + " | tail -1; " + ARCHIVE_GATE_DELETE + "; done")
archive_gate_refused("loop: archive push to ${b}, then --delete of $b joined by ; is refused: ${b} and $b are one name",
                     'for b in a; do ' + VCS + ' push origin "${b}:refs/heads/archive/${b}" 2>&1 | tail -1; '
                     + VCS + ' push origin --delete "$b"; done')
archive_gate_refused("archive push to the taken name archive/feat-2, then --delete feat joined by ; is refused",
                     VCS + " push origin HEAD:refs/heads/archive/feat-2 | tail -1; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push from origin/feat to the taken name archive/feat-2, then --delete feat is refused",
                     VCS + " push origin origin/feat:refs/heads/archive/feat-2 | tail -1; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("incident loop: origin/$b archive push piped to tail, then --delete of $b after ; is refused",
                     'for b in a; do ' + VCS + ' push origin "origin/$b:refs/heads/archive/$b" 2>&1 | tail -1; '
                     + VCS + ' push origin --delete $b; done')

archive_gate_allowed("archive push, then --delete joined by && is allowed",
                     ARCHIVE_GATE_PUSH + " && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push, then :feat joined by && is allowed",
                     ARCHIVE_GATE_REF_PUSH + " && " + ARCHIVE_GATE_COLON_DELETE)
archive_gate_allowed("archive push, && echo with a quoted ;, then --delete is allowed: the quoted ; is text",
                     ARCHIVE_GATE_PUSH + ' && echo "a; b" && ' + ARCHIVE_GATE_DELETE)
archive_gate_allowed("loop body: archive push, then --delete joined by && is allowed",
                     "for _ in 1; do " + ARCHIVE_GATE_PUSH + " && " + ARCHIVE_GATE_DELETE + "; done")
archive_gate_allowed("archive push to archive/feat with 2>&1, then --delete joined by && is allowed",
                     VCS + " push origin HEAD:archive/feat 2>&1 && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push to the taken name archive/feat-2 with 2>&1, then --delete joined by && is allowed",
                     VCS + " push origin HEAD:archive/feat-2 2>&1 && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("a delete with no archive push before it is allowed",
                     ARCHIVE_GATE_DELETE)
archive_gate_allowed("a plain push, then --delete joined by ; is allowed: no archive push, so no gate",
                     VCS + " push origin HEAD:lane/x; " + ARCHIVE_GATE_DELETE)
