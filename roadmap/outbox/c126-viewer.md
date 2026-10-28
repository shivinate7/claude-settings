# c126 viewer fix lane (with d9, c131)

Branch claude/project-thread-xczmrz. Lane session session_013NEJL1Njy2efqjaZTYpMWt.

Status (Oct 28): designer (opus) done, builder (sonnet) running: merge main e0f9e2d, red first, fix.
Designer verdict: the 390 cut is not #713. The `.dsheet` grid's auto column grows to the nowrap
head's min-content (397px at 390 wide; about 417 with CI's fallback font). b41fb51 fitted before the
head text was set. Fix: grid-template-columns minmax(0,1fr), and set the head fields before the fit.
Reconcile: d9's renderer is the one home. #713's .oshot/.ofull renderer is dropped. #713's
tap-picks test is dropped per the d9 ruling, Oct 27 12:13 CDT (a tap opens the viewer).
Open for shiv (does not block): #713 says an option with nothing to draw needs no picture; d9 warns
on every look-question option with no picture. Kept d9.
