# section 21305
FAMILY = "lane-one-topic"
#
# The shipped brief template's role lines, checked as text (rule lane-one-topic). A lane brief is written from this
# template, so its Ask line must name each of the three roles by its label, as a whole word, and no role may be said to
# need no label. These checks sit after section 21304, the first that defines LOG_CHECKS_EXTRA; section 15173 holds the
# send_message and create_session cases that read the same template.
TEMPLATE_ROLE_WORD = {role: re.compile("(?<![A-Za-z0-9])" + re.escape(role) + "(?![A-Za-z0-9])", re.IGNORECASE)
                      for role in ROLES}


def template_ask_case():
    """The shipped template's Ask line names each of the three roles as a whole word. Scope first: one Ask line, then its names."""
    asks = [line for line in BRIEF_TEMPLATE.splitlines() if line.strip().startswith("Ask:")]
    if len(asks) != 1:
        return False, "the template holds %d Ask lines, want one" % len(asks)
    missing = [role for role in ROLES if not TEMPLATE_ROLE_WORD[role].search(asks[0])]
    if missing:
        return False, "the template's Ask line does not name " + ", ".join(missing) + " by label: " + asks[0][:90]
    return True, "the template's Ask line names the Coordinator, Triage and Batch runner"


def template_no_need_no_label_case():
    """The shipped template says no role needs no label: each of the three roles needs its label, as the rule says."""
    for line in BRIEF_TEMPLATE.splitlines():
        if "need no label" in line:
            return False, "the template says a role need no label: " + line[:90]
    return True, "the template says no role need no label"


LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template's Ask line names the Coordinator, Triage and Batch runner",
                         template_ask_case))
LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template says no role need no label", template_no_need_no_label_case))
