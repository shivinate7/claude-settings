# c126 viewer fix lane (with d9, c131)

Round 1 (Oct 28): code review (sonnet) found no ruling broken, 3 low findings. Design review (opus)
failed 2 screens: in the viewer, a wide design is cut (laid out at 390) and the phone title cuts to
"Lay…"; on a pick, the page below drops 23px at 320-390 (`.ready` wraps). Builder round 2 (try 2 of 3)
is running all five fixes. Notes to file: designsOf ignores option designs when the item lists
designs (mixed-shape items only); option letter dropped from the viewer label; no test for the
521-900 px head with a wide font.
