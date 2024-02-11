import os
import subprocess
import sys


def stream_output(process: subprocess.Popen):
    for c in iter(lambda: process.stdout.read(1), b""):
        sys.stdout.buffer.write(c)


def run_host_command(command: list, cwd: str = None):
    print(f"Running host command in {cwd}: " + " ".join(command))
    # we write the command to our hostpipe and let the host execute it
    cd = f"cd {cwd} && " if cwd else ""
    cmd = f"{cd}" + " ".join(command) + "\n"
    with open("/app/hostpipe", "w", encoding="utf-8") as f:
        f.write(cmd)
    # connect output that is written to hostpipe.txt to stdout
    with open("/app/hostpipe.txt", "r", encoding="utf-8") as f:
        for line in f:
            print(line, end="")


def run_command(command: list, cwd: str = None):
    if os.path.exists("/.dockerenv"):
        return run_host_command(command, cwd)
    # pylint: disable=consider-using-with
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
    )
    stream_output(process)
    process.wait()
    return process.returncode
