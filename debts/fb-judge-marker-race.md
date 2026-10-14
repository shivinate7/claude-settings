# The feedback judge can close a newer capture

- **What.** The judge child checks that its message is still the last one, then removes the capture marker. A new owner message in that gap writes a fresh marker, and the child removes it. Capture closes early, and the owner's next plain message is not saved. The gap is microseconds. Found in review round 2 of lane fb-autoclose.
- **Where.** `hooks/feedback_judge.py` lines 49-55, and the marker write in `hooks/local_time.py`.
- **Decision.** `owner-feedback-inbox`.
- **Retire.** Read the marker just before the remove, and remove it only if its stored time matches the judged message. A test writes a newer marker between the check and the remove.
