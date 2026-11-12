# section 21305
FAMILY = "git-after-cd"

# LOG_CHECKS_EXTRA is defined in the diff section (21304), so the git-after-cd crash check registers here.
LOG_CHECKS_EXTRA.append((GIT_AFTER_CD_CRASH_LABEL, git_after_cd_crash_check))

LOG_FAMILY[GIT_AFTER_CD_CRASH_LABEL] = "git-after-cd"
