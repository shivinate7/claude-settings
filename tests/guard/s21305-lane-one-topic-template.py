# section 21305
FAMILY = "lane-one-topic"
#
# The shipped brief template's role lines, checked as text (rule lane-one-topic). A lane brief is written from this
# template, so its Ask line must name each of the three roles by its label, as a whole word, and the template may not tell
# a sender to copy a session id into a brief. These checks sit after section 21304, the first that defines LOG_CHECKS_EXTRA;
# section 15173 holds the
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


# A session id is optional after a label, but the template must not tell a sender to copy one into a brief. The check reads
# each sentence for a copy word with a session, id or roster word.
COPY_WORD = re.compile(r"\bcop(?:y|ies|ied|ying)\b", re.IGNORECASE)
ID_WORD = re.compile(r"\bsessions?\b|\bids?\b|\broster\b", re.IGNORECASE)


def template_no_copy_id_case():
    """The shipped template tells no sender to copy a session id into a brief. Scope first: the template holds an Ask line,
    so its text is read. The template is hard-wrapped, so each paragraph is joined before its sentences are read."""
    if not any(line.strip().startswith("Ask:") for line in BRIEF_TEMPLATE.splitlines()):
        return False, "the template holds no Ask line, so its text is not read"
    for paragraph in re.split(r"\n\s*\n", BRIEF_TEMPLATE):
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(paragraph.split())):
            if COPY_WORD.search(sentence) and ID_WORD.search(sentence):
                return False, "the template tells a sender to copy a session id into a brief: " + sentence[:90]
    return True, "the template tells no sender to copy a session id into a brief"


LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template's Ask line names the Coordinator, Triage and Batch runner",
                         template_ask_case))
LOG_CHECKS_EXTRA.append(("lane-one-topic: the shipped brief template tells no sender to copy a session id into a brief",
                         template_no_copy_id_case))
