# section 17501
FAMILY = "conflict-markers"

# The failed cd ends the && chain, so the later cd into the triplet repo never runs and the commit never runs.
cmk_allow("a cd into a missing folder, then && a cd into a triplet repo, then && add -A and commit, the chain is skipped",
          "cd " + slash(CMK_GONE) + " && cd " + slash(CMK_CLT) + " && " + VCS + " add -A && " + VCS + " commit -m x",
          NOGIT)

# An echo the tokenizer cannot read (its ANSI-C quote holds an escaped quote) must not hide the cd before it:
# the commit still runs in the folder that cd named, the triplet repo.
cmk_refuse("a cd into a repo with a triplet tracked, then ; an echo the tokenizer cannot read, then add -A and commit",
           "cd " + slash(CMK_CLT) + "; echo $'it\\'s'; " + VCS + " add -A && " + VCS + " commit -m x", NOGIT)
