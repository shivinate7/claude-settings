# section 43821
FAMILY = "pinned-string-unknown"
#
# `pinned-string-unknown`. A stamp's merge.requiredChecks string that the loaded merge tool does not pin (its PINNED_STRINGS
# lacks it) reads as no pin, so the merge check falls back to the branch protection and refuses nothing. The guard must
# refuse such a head as unknown, and the refusal names the string (rule merge-checks). The pinned strings and the
# protection keep their verdicts. The fixtures are in tests/guard/s13406-merge.py: STAMPUNKNOWN and STAMPPROTECT, beside
# STAMPREPO (a pinned list) and FIRST_PROOF_REPO and STAMPNOCHECK (the first-proof and none pins, already covered there).
#
# THE RED. The merge tool of this checkout pins "none" and "first-proof" only, so "all-proof" is a string it lacks. GHPASSCHK
# answers one check named checks, green. Under the protection that head is green, so today the merge is allowed.
add("pinned-string-unknown: a stamp requiredChecks string the merge tool does not pin is refused unknown, and the refusal names it",
    "deny", rule="merge-checks", tool="mcp__github__merge_pull_request", cwd=STAMPUNKNOWN, pullNumber=12, repo="x", owner="y",
    carries=("unknown", "all-proof"), env_path=GHPASSCHK + os.pathsep + PY_PATH)

# THE CONTROLS. Each differs from the red by one thing, and keeps its verdict today and after the fix.
# The protection string: the same green head, the same protection read, no pin: allowed. It is the twin of the red above.
add("pinned-string-unknown: the protection string keeps the branch protection read, so the same green head is allowed",
    "allow", silent=True, tool="mcp__github__merge_pull_request", cwd=STAMPPROTECT, pullNumber=12, repo="x", owner="y",
    env_path=GHPASSCHK + os.pathsep + PY_PATH)
# A pinned list is the required list: STAMPREPO pins checks, and the same green head answers that check: allowed.
add("pinned-string-unknown: a pinned requiredChecks list keeps its own required list, so the same green head is allowed",
    "allow", silent=True, tool="mcp__github__merge_pull_request", cwd=STAMPREPO, pullNumber=12, repo="x", owner="y",
    env_path=GHPASSCHK + os.pathsep + PY_PATH)
