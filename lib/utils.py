import logging
import os
import subprocess
from typing import Dict, List

logger = logging.getLogger(__name__)


# func that reads .env file into a dictionary
def read_env_file(file: str) -> Dict[str, str]:
    with open(file, "r", encoding="utf-8") as f:
        return dict(line.strip().split("=", 1) for line in f if not line.strip().startswith("#") and "=" in line)


def run_command(command: List[str], cwd: str = None) -> int:
    env_file = f"{cwd}/.env" if cwd else ""
    env = read_env_file(env_file) if env_file != "" and os.path.exists(env_file) else {}
    try:
        with open("logs/proxy.log", "w", encoding="utf-8") as f:
            process = subprocess.run(
                command,
                check=True,
                cwd=cwd,
                env=env,
                stdout=f,
                stderr=f,
            )
        return process.returncode
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)} (exit code: {e.returncode})")
        raise


def run_command_output(command: List[str], cwd: str = None) -> str:
    """Run command and return stdout as string"""
    env_file = f"{cwd}/.env" if cwd else ""
    env = read_env_file(env_file) if env_file != "" and os.path.exists(env_file) else {}
    try:
        process = subprocess.run(
            command,
            check=True,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return process.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)} (exit code: {e.returncode})")
        raise
