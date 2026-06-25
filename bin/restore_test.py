import os
import shutil
import sys
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.restore import main


class TestRestoreDispatcher(unittest.TestCase):
    """Real-boundary test: a real archive on disk, extraction + real adapter
    scripts, with only the S3 download/list mocked."""

    def setUp(self) -> None:
        self._prev_root = os.environ.get("ITSUP_ROOT")
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        os.environ["ITSUP_ROOT"] = str(self.root)
        (self.root / "pyproject.toml").write_text("[project]\n")

        secrets = self.root / "secrets"
        secrets.mkdir()
        (secrets / "itsup.txt").write_text(
            "AWS_ACCESS_KEY_ID=test-access-key\n"
            "AWS_SECRET_ACCESS_KEY=test-secret-key\n"
            "AWS_S3_HOST=s3.test.com\n"
            "AWS_S3_REGION=us-test-1\n"
            "AWS_S3_BUCKET=test-bucket\n"
        )
        self.key = "itsup.tar.gz.20260101000000"

    def tearDown(self) -> None:
        if self._prev_root is None:
            os.environ.pop("ITSUP_ROOT", None)
        else:
            os.environ["ITSUP_ROOT"] = self._prev_root
        self._tmp.cleanup()

    def _build_archive(self, files: dict[str, str]) -> Path:
        """Build a tar.gz whose members mirror backup.py's layout."""
        content = self.root / "_archive_src"
        for arcname, body in files.items():
            path = content / arcname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        archive = self.root / "_archive.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for arcname in files:
                tar.add(content / arcname, arcname=arcname)
        shutil.rmtree(content)
        return archive

    def _mock_s3(self, archive: Path) -> mock.MagicMock:
        s3_client = mock.MagicMock()
        s3_client.list_objects_v2.return_value = {"Contents": [{"Key": self.key}]}
        s3_client.download_file.side_effect = lambda bucket, key, dest: shutil.copy(archive, dest)
        return s3_client

    def _write_adapter_project(self, name: str, restore_body: str) -> None:
        pdir = self.root / "projects" / name
        pdir.mkdir(parents=True)
        (pdir / "backup.yml").write_text(f"adapter: {name}\nexclude: [data]\n")
        script = pdir / "backup-adapter.sh"
        script.write_text(restore_body)
        script.chmod(0o755)

    def test_restore_non_adapter_project_filesystem_extract(self) -> None:
        """A project without an adapter is restored as a filesystem extract."""
        archive = self._build_archive({"upstream/web/index.html": "<h1>hi</h1>"})
        with mock.patch("boto3.client", return_value=self._mock_s3(archive)):
            main(["web", "--yes"])

        self.assertEqual((self.root / "upstream" / "web" / "index.html").read_text(), "<h1>hi</h1>")

    def test_restore_proxy_target(self) -> None:
        """The proxy target extracts archived proxy/ state into place."""
        archive = self._build_archive({"proxy/acme.json": "{}", "upstream/web/x": "y"})
        with mock.patch("boto3.client", return_value=self._mock_s3(archive)):
            main(["proxy", "--yes"])

        self.assertEqual((self.root / "proxy" / "acme.json").read_text(), "{}")
        # proxy target does not touch upstream projects.
        self.assertFalse((self.root / "upstream" / "web").exists())

    def test_restore_adapter_project_runs_adapter_restore(self) -> None:
        """An adapter-backed project routes its dump to the adapter's restore verb."""
        # The adapter reads its _backup/ and writes a marker proving invocation.
        self._write_adapter_project(
            "postgres",
            '#!/usr/bin/env sh\nset -eu\n'
            'if [ "$1" = "restore" ]; then\n'
            '  cat "$2/_backup/db.dump" > "$2/restored.marker"\n'
            "fi\n",
        )
        archive = self._build_archive({"upstream/postgres/_backup/db.dump": "ROWS"})
        with mock.patch("boto3.client", return_value=self._mock_s3(archive)):
            main(["postgres", "--yes"])

        marker = self.root / "upstream" / "postgres" / "restored.marker"
        self.assertEqual(marker.read_text(), "ROWS")

    def test_restore_all_routes_each_project_and_proxy(self) -> None:
        """'all' restores every archived project plus proxy state."""
        archive = self._build_archive(
            {
                "upstream/web/index.html": "page",
                "upstream/api/app.py": "code",
                "proxy/traefik.yml": "cfg",
            }
        )
        with mock.patch("boto3.client", return_value=self._mock_s3(archive)):
            main(["all", "--yes"])

        self.assertEqual((self.root / "upstream" / "web" / "index.html").read_text(), "page")
        self.assertEqual((self.root / "upstream" / "api" / "app.py").read_text(), "code")
        self.assertEqual((self.root / "proxy" / "traefik.yml").read_text(), "cfg")

    def test_guard_aborts_without_confirmation(self) -> None:
        """Without --yes and a non-affirmative answer, restore aborts before any write."""
        archive = self._build_archive({"upstream/web/index.html": "data"})
        s3_client = self._mock_s3(archive)
        with mock.patch("boto3.client", return_value=s3_client):
            with mock.patch("builtins.input", return_value="n"):
                with self.assertRaises(SystemExit) as ctx:
                    main(["web"])

        self.assertEqual(ctx.exception.code, 1)
        # The guard fires before any download/extract, so nothing was written.
        s3_client.download_file.assert_not_called()
        self.assertFalse((self.root / "upstream" / "web").exists())

    def test_guard_proceeds_under_yes(self) -> None:
        """--yes bypasses the prompt and the restore proceeds."""
        archive = self._build_archive({"upstream/web/index.html": "data"})
        with mock.patch("boto3.client", return_value=self._mock_s3(archive)):
            main(["web", "--yes"])

        self.assertTrue((self.root / "upstream" / "web" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
