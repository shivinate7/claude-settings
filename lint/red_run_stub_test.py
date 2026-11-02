"""A stand-in for lint/check_red_run.py that exits 0 and prints nothing.

lint/test_check_red_run.py runs against it for the red-run record. Each case that expects a flag
then fails on its exit-code assertion, which is a behavioural red and not a missing module.
"""
import sys

sys.exit(0)
