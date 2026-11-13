# section 35537
FAMILY = "push-delete"
LOG_CHECKS_EXTRA.append(("push: a failing ARGV_GAP over 48000 spaces stays linear in CPU", argv_gap_case))
LOG_CHECKS_EXTRA.append(("push: a run of deno eval flags before a nested quote stays linear in CPU",
                         argv_flag_gap_case))


# Ssh words in one echo, then a forced push in a python -c quote. Each `ssh` word is judged as a command, and
# each judge re-reads the words after it, so the cost grows as the square of the count. 2000 words is 12000
# characters. The bare `ssh a` chain has no echo in front, and is left out: it reads as a command chain.
def echo_ssh_cmd(n):
    return "echo " + "ssh a " * n + '; python3 -c "import os; os.system(\\"' + VCS + ' push -f origin x\\")"'


def echo_ssh_case():
    return rm_var_ratio(echo_ssh_cmd, 125, 2000, must="force-push", cwd=PUSHFEAT)


LOG_CHECKS_EXTRA.append(("push: 2000 ssh words before a nested forced push stay linear in CPU", echo_ssh_case))
LOG_CHECKS_EXTRA.append(("roadmap-one-writer: a push starts one rev-parse, one more for a stray push, symbolic-ref for a refspec, "
                         "HEAD and bare, push.default for bare only, one config read of the remote for a literal main destination, "
                         "no read for HEAD:<branch>, a --all or glob push reads the remote's URL and its tracking refs, "
                         "one rev-list for each pushed ref not to main or master, "
                         "and reads the transcript only at the record branch",
                         record_push_cost_case))
