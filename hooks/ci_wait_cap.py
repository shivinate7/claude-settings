#!/usr/bin/env python3
"""The CI-wait cap: the most minutes a check-in that waits on CI may wait.

The number is a dated fact about the prompt cache, kept with its source in hooks/ci_wait_cap.json.
Read it through cap_minutes(). Standard library only.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def cap_path():
    return os.path.join(HERE, "ci_wait_cap.json")


def cap_minutes():
    """The cap in whole minutes, read from the data file on each call.

    A missing, unreadable or malformed file raises. A silent default would hide a lost source.
    """
    with open(cap_path(), encoding="utf-8") as handle:
        value = json.load(handle)["cap_minutes"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("cap_minutes in %s is not a positive whole number: %r" % (cap_path(), value))
    return value
