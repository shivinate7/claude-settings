"""A stand-in for the checks that a stub run replaces. It reports nothing.

lint/test_check_red_run.py runs it as a script for the red-run record. Each case that expects a flag
then fails on its exit-code assertion, which is a behavioural red and not a missing module.
lint/test_check_hook_output_pins.py loads its find_pins and Unknown, which finds no pin and raises
nothing. Run as a script it exits 0 and prints nothing.
"""
import sys


class Unknown(Exception):
    pass


def find_pins(root):
    return []


def main(argv):
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
