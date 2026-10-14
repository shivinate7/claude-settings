# The decision-watch slot timers are computed, not measured

- **What.** Each step that holds the slot has a mod timer: each python finder 6 s (two per run), each python run 31 s (a 30 s host limit, unmeasured against a real run), the model call 50 s, each toast 5 s (a verdict and up to three notices), each log write 2 s (up to six). The sum is about 168 s, computed, not measured. A timer frees the slot but does not stop the host call or kill the child. The `$.env.get` reads have no timer.
- **Where.** The step timers in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** Measure each step on this machine, set each timer from the measured figure, and put a timer on the `$.env.get` reads.
