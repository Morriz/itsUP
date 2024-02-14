import subprocess
import sys
from typing import Any, List


def stream_output(process: subprocess.Popen[Any]) -> None:
    for c in iter(lambda: process.stdout.read(1), b""):
        sys.stdout.buffer.write(c)


def run_command(command: List[str], cwd: str = None) -> int:
    # pylint: disable=consider-using-with
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
    )
    stream_output(process)
    process.wait()
    return process.returncode
