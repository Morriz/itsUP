import subprocess
from typing import List


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
