import subprocess
import sys


def stream_output(process: subprocess.Popen):
    for c in iter(lambda: process.stdout.read(1), b""):
        sys.stdout.buffer.write(c)
