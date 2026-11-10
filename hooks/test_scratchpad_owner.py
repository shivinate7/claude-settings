#!/usr/bin/env python3
# The full guard suite runs past the 600 s limit of a debt's Retire check (lint/check_debt_retire.py), so the
# scratchpad-owner debts name this file: it runs only that family of hooks/test_guard.py and exits with its code.
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, GUARD_FAMILY="scratchpad-owner")
sys.exit(subprocess.run([sys.executable, os.path.join(HERE, "test_guard.py")],
                        cwd=os.path.dirname(HERE), env=ENV).returncode)
