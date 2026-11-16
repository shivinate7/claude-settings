# section 42915
# Rule lane-step-dup, part two, in the lane-start pass (branch lane-start-one-pass). A lane start that breaks another
# lane-start rule and holds a step an open lane pull request holds is refused under lane-step-dup and names that pull
# request, as main does. The pass refuses under the first broken rule and never reaches the pull request read.
FAMILY = "lane-step-dup-pr"

# Refused: effort high breaks lane-effort-pin, and the open pull request holds the step. main refuses under lane-step-dup
# and names #13; the one lane-start pass files the start under lane-effort-pin and never reaches the pull request read.
# The control is steppr_create's effort-medium refusal in section 42910, which the code already refuses.
steppr_create("a create_session with effort high that holds a step an open pull request holds is refused under lane-step-dup, and names the pull request",
              "deny", fake_gh_path(ARCHOPEN), effort="high", carries=(STEPPR_PR, "has the head of step"))
