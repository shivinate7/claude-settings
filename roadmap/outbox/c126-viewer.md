# c126 viewer fix lane (with d9, c131)

Branch claude/project-thread-xczmrz, head bce10f6 (pushed). Lane session session_013NEJL1Njy2efqjaZTYpMWt.

Status (Oct 28): built (builder sonnet). Merge of main e0f9e2d is 58a69e7; red test 658dbb5 (Close's
right edge was 404 at 390 wide); fix bce10f6. Local gates pass: page.test.mjs, test_reply_judge,
test_call_judge, ci-job gates --lint, ste-changed origin/main. Design reviewer (opus) and code
reviewer (sonnet, round 1) are running. No draft PR yet.
Cause (designer, opus): the `.dsheet` grid's auto column grew to the nowrap head's min-content.
Fix: grid-template-columns minmax(0,1fr), and set the head fields before the fit.
Reconcile: d9's renderer is the one home for the option-card picture. #713's renderer and its
tap-picks test are dropped per the d9 ruling (Oct 27 12:13 CDT).
Ruled (shiv, Oct 27 23:40 CDT): every look-question option shows a picture; d9's warning stays.
