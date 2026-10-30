# Inbox saves agent reports as owner messages

- **What.** A subagent's hand-back reaches the session as a prompt that starts with `<agent-message`. The inbox capture saves it as an owner message, and the feedback guard then asks for items under it. In lane page-answer-send (Oct 30) this fired on each of ten hand-backs; each was jotted as a note by hand.
- **Where.** The capture in `hooks/local_time.py` and its skip list, `MACHINE_TAGS` in `hooks/shared_names.py`.
- **Decision.** `owner-feedback-inbox` (each owner message gets item lines).
- **Retire.** The capture skips a prompt that starts with the agent-message tag, and a case proves it.
