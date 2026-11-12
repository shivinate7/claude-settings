"""A stand-in for lint/check_waiting_copy_backup.py that exits 0 and prints nothing.

lint/test_check_waiting_copy_backup.py runs against it through WAITING_COPY_CHECK_UNDER_TEST, for the
red-run record (the test-practices decision, P3). Each case that expects a finding then fails on its
exit-code assertion, which is a behavioural red and not a missing module.
"""
import sys

sys.exit(0)
