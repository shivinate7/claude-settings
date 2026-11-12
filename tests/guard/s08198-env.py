# section 8198
FAMILY = "env"
FAMILIES["env"] = "environment files"
sh("env: a PowerShell backtick pair before ; then a read of the env file, denies",
   "echo a``; cat " + ENV, "deny", "env-file", tool="PowerShell", cwd=NOGIT)


# =========================================================================== 2d. the silent write
