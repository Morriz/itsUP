"""Verified Postgres backup/restore round-trip against a REAL disposable container.

A mocked compose-exec boundary proves only orchestration and stays green on a
restore that silently loses data — exactly the failure this work exists to close.
Data equivalence can only be proven by a real engine, so this test spins an
ephemeral postgres container, seeds known data, runs the real adapter dump, wipes
the database, runs the real adapter restore into the running instance, and asserts
row-level equivalence. It skips with a clear reason when docker is unavailable.
"""

import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ADAPTER = Path(__file__).resolve().parent / "backup-adapters" / "postgres.sh"

COMPOSE = """\
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: testpass
"""


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=15)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


@unittest.skipUnless(_docker_available(), "docker is not available — skipping real Postgres round-trip")
class TestPostgresRoundTrip(unittest.TestCase):
    """Seed -> dump -> wipe -> restore -> assert equivalence, all against a real engine."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.upstream = Path(self._tmp.name) / "postgres"
        self.upstream.mkdir(parents=True)
        (self.upstream / "docker-compose.yml").write_text(COMPOSE)
        self._compose("up", "-d")
        self._wait_ready()

    def tearDown(self) -> None:
        # Always tear the container + volumes down, even on assertion failure.
        try:
            self._compose("down", "-v", check=False)
        finally:
            self._tmp.cleanup()

    def _compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=self.upstream,
            capture_output=True,
            text=True,
            check=check,
        )

    def _psql(self, db: str, sql: str) -> str:
        result = self._compose("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", db, "-tAc", sql)
        return result.stdout.strip()

    def _wait_ready(self) -> None:
        for _ in range(60):
            ready = self._compose("exec", "-T", "postgres", "pg_isready", "-U", "postgres", check=False)
            if ready.returncode == 0:
                return
            time.sleep(1)
        self.fail("postgres container did not become ready in time")

    def _adapter(self, verb: str) -> None:
        subprocess.run([str(ADAPTER), verb, str(self.upstream)], env=os.environ.copy(), check=True)

    def test_dump_restore_preserves_rows(self) -> None:
        # Seed known data in a non-default database.
        self._psql("postgres", "CREATE DATABASE appdb;")
        self._psql("appdb", "CREATE TABLE t (id int PRIMARY KEY, name text);")
        self._psql("appdb", "INSERT INTO t VALUES (1, 'alpha'), (2, 'beta');")
        seeded = self._psql("appdb", "SELECT id, name FROM t ORDER BY id;")
        self.assertEqual(seeded, "1|alpha\n2|beta")

        # Dump via the real adapter.
        self._adapter("dump")
        self.assertTrue((self.upstream / "_backup" / "globals.sql").exists())
        self.assertTrue((self.upstream / "_backup" / "appdb.dump").exists())

        # Simulate data loss: drop the database entirely.
        self._psql("postgres", "DROP DATABASE appdb;")
        self.assertNotIn("appdb", self._psql("postgres", "SELECT datname FROM pg_database;"))

        # Restore via the real adapter into the running instance.
        self._adapter("restore")

        # The restored rows must equal what was dumped.
        restored = self._psql("appdb", "SELECT id, name FROM t ORDER BY id;")
        self.assertEqual(restored, seeded)


if __name__ == "__main__":
    unittest.main()
