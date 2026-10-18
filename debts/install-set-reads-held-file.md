# Install-set test reads a file a child still holds

- **What.** On Windows the install-set test reads a hook run's output file while another process still holds it, so the job fails with an IOException though the install is correct. It blocked a merge on 2026-10-17 (run 39078600480); the same tree passed before and after.
- **Where.** `install-set.test.ps1` near line 254, the `ReadAllText` of `lock1-hook/hook-b-run.out.txt`, in the pointer-windows job.
- **Decision.** none
- **Retire.** Wait for the child to exit, or retry the read on a sharing error, before reading its output; the pointer-windows job passes on repeat runs.
