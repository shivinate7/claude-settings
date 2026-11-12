# section 17502
FAMILY = "conflict-markers"

# A `>` inside the echo's quotes is text, not a redirect. It must not make the commit after it blind to the triplet.
cmk_refuse("a cd into a repo with a triplet tracked, then ; an echo with a quoted greater-than, then add -A and commit",
           "cd " + slash(CMK_CLT) + "; echo \"a > b\"; " + VCS + " add -A && " + VCS + " commit -m x", NOGIT)

# Scanner traps: an escaped quote, or a lone apostrophe, must not end the quote early and hide the redirect after it.
# The echo then reaches the tree, so the commit after it is blind here (a push after it is refused as a chain).
cmk_allow("a cd into a repo with a triplet tracked, then ; an echo with an escaped quote and a redirect, then add -A and commit",
          "cd " + slash(CMK_CLT) + "; echo \"a\\\"b\" > x; " + VCS + " add -A && " + VCS + " commit -m x", NOGIT)

cmk_allow("a cd into a repo with a triplet tracked, then ; an echo with a lone apostrophe and a redirect, then add -A and commit",
          "cd " + slash(CMK_CLT) + "; echo don't > x; " + VCS + " add -A && " + VCS + " commit -m x", NOGIT)
