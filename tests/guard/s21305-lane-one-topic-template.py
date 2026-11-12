# section 21305
FAMILY = "lane-one-topic"
#
# The shipped brief template's role lines, checked as text (rule lane-one-topic). A lane brief is written from this
# template, so its role lines must name the Coordinator alone. These checks sit after section 21304, the first that
# defines LOG_CHECKS_EXTRA; section 15173 holds the send_message and create_session cases that read the same template.


def template_ask_case():
    """The shipped template's Ask line names the Coordinator and neither other role. Scope first: one Ask line, then its names."""
    asks = [line for line in BRIEF_TEMPLATE.splitlines() if line.strip().startswith("Ask:")]
    if len(asks) != 1:
        return False, "the template holds %d Ask lines, want one" % len(asks)
    if "Coordinator" not in asks[0]:
        return False, "the template's Ask line names no Coordinator: " + asks[0][:90]
    named = [role for role in OTHER_ROLES if role in asks[0]]
    if named:
        return False, "the template's Ask line names " + " and ".join(named) + ": " + asks[0][:90]
    return True, "the template's Ask line names the Coordinator and no other role"


def template_no_three_roles_case():
    """The shipped template's guidance names no three roles: the rule asks for the Coordinator label only."""
    if "three roles" in BRIEF_TEMPLATE:
        return False, "the template still says three roles, where the rule asks for the Coordinator label only"
    return True, "the template names no three roles"


LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template's Ask line names the Coordinator and no other role",
                         template_ask_case))
LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template says no three roles", template_no_three_roles_case))
