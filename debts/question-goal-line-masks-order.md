# A decorated Goal line hides a late Problem line

- **What.** A decorated Goal line earlier in the question, such as `- goal: old`, masks a real Problem-first order. The order check reads that line first, so it passes. Presence passes too, on the later plain `Goal:` line.
- **Where.** The order check in `hooks/question_outcome.py`.
- **Decision.** `question-outcome-check` (each question passes an outcome check before the owner sees it).
- **Retire.** The order check reads the first Goal line the owner would count, and a case with `- goal: old` before a late Problem line is denied.
