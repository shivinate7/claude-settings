import subprocess
import sys


def test_run():
    subprocess.run([sys.executable, "src/retry.py"], check=True)
