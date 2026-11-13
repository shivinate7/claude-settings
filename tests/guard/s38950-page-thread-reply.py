# section 38950
FAMILY = "misc"
#
# Rule page-thread-reply. Ruling: owner, Oct 28 02:44 CDT, decision questions-go-to-owner ("Answer on the page,
# not in a comment thread"); owner R18, Nov 10 16:55 CST, point 4. A session never replies into a comment thread
# on its repo's waiting page. The refusal's remedy: rewrite the item the comment is about, and say in one line in
# the session what changed. Reads, watches, other artifacts, GitHub review threads and item rewrites pass.
#
# Fixtures: PQ_REPO and PQ_URL come from the port-question section (its layout-extras names PQ_URL as the page),
# and up_item from the uniform-pick section. A case here adds only its own call.

PTR_RULE = "page-thread-reply"
PTR_REMEDY = ("rewrite the item", "one line")
PTR_NAME = "page thread reply: "
PTR_THREAD = "thread-1"
PTR_TEXT = "The item is rewritten; the answer is on the page."
PTR_OTHER = "https://claude.ai/artifact/otherpage"


def ptr_refuse(name, **fields):
    add(PTR_NAME + name, "deny", PTR_RULE, carries=PTR_REMEDY, tool="ArtifactComments", cwd=PQ_REPO, **fields)


def ptr_allow(name, **fields):
    add(PTR_NAME + name, "allow", None, tool="ArtifactComments", cwd=PQ_REPO, **fields)


# Refused: any reply into a thread on this repo's waiting page, whatever its text or flags.
ptr_refuse("a reply into a thread on the waiting page is denied",
           action="reply", url=PQ_URL, thread_id=PTR_THREAD, text=PTR_TEXT)
ptr_refuse("a one-word reply on the waiting page is denied",
           action="reply", url=PQ_URL, thread_id=PTR_THREAD, text="Done.")
ptr_refuse("a reply sent with acknowledge_duplicate is denied",
           action="reply", url=PQ_URL, thread_id=PTR_THREAD, text=PTR_TEXT, acknowledge_duplicate=True)
ptr_refuse("an empty reply on the waiting page is denied",
           action="reply", url=PQ_URL, thread_id=PTR_THREAD, text="")
ptr_refuse("a reply of the largest size on the waiting page is denied",
         action="reply", url=PQ_URL, thread_id=PTR_THREAD, text="x" * 4096)

# Passes: every call that is not a reply into a thread on the waiting page.
ptr_allow("a reply into a thread on another artifact is allowed",
          action="reply", url=PTR_OTHER, thread_id=PTR_THREAD, text=PTR_TEXT)
ptr_allow("a read of the waiting page is allowed", action="read", url=PQ_URL)
ptr_allow("a read of one thread on the waiting page is allowed", action="read", url=PQ_URL, thread_id=PTR_THREAD)
ptr_allow("a read of another artifact is allowed", action="read", url=PTR_OTHER)
# The waiting-page skill has a session watch the page with this action (SKILL.md, "watch"). A refused watch breaks wakes.
ptr_allow("a watch of the waiting page is allowed", action="watch", url=PQ_URL)
ptr_allow("a watch that stops on the waiting page is allowed", action="watch", url=PQ_URL, on=False)
ptr_allow("a bare watch listing is allowed", action="watch")
add(PTR_NAME + "a reply on a GitHub pull request review thread is allowed", "allow", None,
    tool="mcp__github__add_reply_to_pull_request_comment", cwd=PQ_REPO, body="Fixed in the next push.")
# An item rewrite is the remedy, so it must pass. up_item's pick is the non-widening option, which passes uniform-pick.
add(PTR_NAME + "an item rewrite on the waiting page is allowed", "allow", None, tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="set", collection="items", doc_id="banchi-titles", data=up_item(pick="b", why="One form."))
# A resolve is not a reply, so it passes. The ruling names replies only; this pins the action gate, so a
# mutant that refuses resolve goes red.
ptr_allow("a resolve of a thread on the waiting page is allowed", action="resolve", url=PQ_URL, thread_id=PTR_THREAD)

# A reply is refused whatever form the page's url takes: the /code/artifact/ form with a query, a bare id, or
# an http url. The guard compares artifact ids (lint/layout.py artifact_id), so these pin that reader.
ptr_refuse("a reply on the waiting page at its /code/artifact/ url with a query is denied",
           action="reply", url="https://claude.ai/code/artifact/pqpage?tab=questions", thread_id=PTR_THREAD,
           text=PTR_TEXT)
ptr_refuse("a reply on the waiting page with its bare id as the url is denied",
           action="reply", url="pqpage", thread_id=PTR_THREAD, text=PTR_TEXT)
ptr_refuse("a reply on the waiting page at an http url is denied",
           action="reply", url="http://claude.ai/artifact/pqpage", thread_id=PTR_THREAD, text=PTR_TEXT)

# A reply with no url, in a repo that has a waiting page, is refused: nothing says which artifact it lands in.
ptr_refuse("a reply with no url in a repo with a waiting page is denied",
           action="reply", thread_id=PTR_THREAD, text=PTR_TEXT)
# A reply with no url, in a repo with no waiting page, names no page of this repo, so it is allowed. This pins the
# has_waiting_page half of the no-url refusal: a mutant that refuses every no-url reply goes red here.
add(PTR_NAME + "a reply with no url in a repo with no waiting page is allowed", "allow", None,
    tool="ArtifactComments", cwd=NOGIT, action="reply", thread_id=PTR_THREAD, text=PTR_TEXT)
# An empty url string names no artifact. It is a string, so the no-url branch does not see it: the page check must
# refuse it on the url's own id, as a reply with no url is refused.
ptr_refuse("a reply with an empty url in a repo with a waiting page is denied",
           action="reply", url="", thread_id=PTR_THREAD, text=PTR_TEXT)
