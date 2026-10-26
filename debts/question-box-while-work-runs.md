# No check refuses a question box while work runs

- **What.** A session can open a question box while its agents, lanes or background commands run. The box stops the session until the owner answers, and the running work goes on with no brake. Rule `questions-go-to-owner` (questions go to the owner) forbids it. No check refuses it.
- **Where.** The AskUserQuestion agent hook in `settings.json`. It judges the box alone. Whether it can read the transcript, and so see which agents run, is unmeasured. The only reader of this session's live agents is the host's agent list in a mod (`mods/session-board`, the session board), which observes and refuses nothing.
- **Decision.** `questions-go-to-owner` (questions go to the owner), ruling 3b.
- **Retire.** First measure whether the agent hook can read the transcript; if it can, the check may fit there. A check refuses AskUserQuestion while this session has a live agent or background command, and lets it through with none. A test shows both, red on main first. Then delete this file.
