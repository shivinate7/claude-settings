# The boot check skips xcodebuild boots

**What.** The ruling 5 boot check runs only after `simctl boot` and MCP `launch`. Three other boot routes are recorded but not checked: `xcodebuild -destination`, `simctl bootstatus -b`, and a `simctl boot` with a flag before the device. A half-booted device from those routes goes unseen.

**Where.** `hooks/sim_boot_record.py`, the PostToolUse branch.

**Decision.** sweep-shuts-down-idle-simulators, ruling 5 (boot check).

**Retire.** The check also runs after an xcodebuild boot, and a case in `hooks/test_sim_boot_record.py` shows it.
