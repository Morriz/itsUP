import os
import subprocess
from typing import Dict, List


# functhan that reads .env file into a dictionary
def read_env_file(file: str) -> Dict[str, str]:
    with open(file, "r") as f:
        return dict(line.strip().split("=", 1) for line in f if not line.strip().startswith("#") and "=" in line)


def run_command(command: List[str], cwd: str = None) -> int:
    env_file = f"{cwd}/.env" if cwd else ""
    env = read_env_file(env_file) if not env_file == "" and os.path.exists(env_file) else {}
    with open("logs/error.log", "w", encoding="utf-8") as f:
        process = subprocess.run(
            command,
            check=True,
            cwd=cwd,
            env=env,
            stdout=f,
            stderr=f,
        )
    return process.returncode
