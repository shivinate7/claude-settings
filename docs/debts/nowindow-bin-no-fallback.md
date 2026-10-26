# Bin tools import the no-window helper bare

- **What.** bin/verdict, bin/ste-changed, bin/ci-job and merge/launch.py import hooks/_nowindow.py with no fallback, so a copy-mode install that lands bin/ before hooks/ makes them fail.
- **Where.** bin/verdict, bin/ste-changed, bin/ci-job, merge/launch.py.
- **Decision.** `spawns-use-no-window` (helper programs start with no window).
- **Retire.** Give each the same ImportError fallback the hooks use. Check: a test copies each tool without the helper and runs it.
