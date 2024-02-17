import subprocess
import sys
from typing import Any, List


def stream_output(process: subprocess.Popen[Any]) -> None:
    for c in iter(lambda: process.stdout.read(1), b""):
        sys.stdout.buffer.write(c)


def run_command(command: List[str], cwd: str = None) -> int:
    with open("logs/error.log", "w", encoding="utf-8") as f:
        process = subprocess.run(
            command,
            check=True,
            cwd=cwd,
            stdout=f,
            stderr=f,
        )
    return process.returncode
