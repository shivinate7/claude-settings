# The inbox capture drops a prompt that an app block leads

**What.** `capture` skips any prompt that starts with a `MACHINE_TAGS` tag. A desktop app block opens with `<system-reminder>`, which is in that list, so the owner's typed words after it are never saved, and no line says so. This is the reverse of the debt on notices that the feedback inbox saves.

**Where.** `hooks/local_time.py`, `capture`, the prefix check against `MACHINE_TAGS` at line 251. The tag list is `hooks/shared_names.py` `MACHINE_TAGS`. The rule that owner prompts are saved is in owner-feedback-inbox (a decision on the owner's feedback inbox), its Notices bullet at about line 34.

**Decision.** owner-override (an owner override lets a refused or asked act through).

**Retire.** Closed when `capture` saves a prompt that an app block leads and still skips a bare notice. `hooks/test_local_time.py` gets a red case: an app block, then owner words, is saved; a prompt that starts with a notice tag is not.
