# A partial inbox write can leave a fence open

- **What.** A partial write can leave a fence open. Later blocks then read as one message with no items, and the gate repeats that block. It needs a disk-full failure.
- **Where.** The inbox write in the capture hook.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to an inbox before the turn ends).
- **Retire.** The inbox write is atomic, with a temp file and a rename, and a test pins it.
