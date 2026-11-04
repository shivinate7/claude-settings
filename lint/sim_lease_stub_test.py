"""A stand-in for bin/sim-lease, for the red-run record of lint/test_sim_lease.py.

Main has no bin/sim-lease, so a case run there errors on the missing file, and an error is not a red. This
stand-in answers every case with a behaviour instead: take refuses at once with no output, and give and status
exit 0 with no output. Each case then fails on its own assert. Run it with SIM_LEASE=lint/sim_lease_stub_test.py.
"""
import sys

sys.exit(1 if sys.argv[1:2] == ["take"] else 0)
