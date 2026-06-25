import io
import os
import sys
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from botocore.config import Config

from bin.backup import main


class TestBackupScript(unittest.TestCase):
    """Real-boundary test: tar a real upstream tree under ITSUP_ROOT, upload via a mocked S3 client."""

    def setUp(self) -> None:
        self._prev_root = os.environ.get("ITSUP_ROOT")
        self._prev_cwd = os.getcwd()
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        os.environ["ITSUP_ROOT"] = str(root)

        upstream = root / "upstream" / "proj"
        upstream.mkdir(parents=True)
        (upstream / "data.txt").write_text("payload")

        secrets = root / "secrets"
        secrets.mkdir()
        (secrets / "itsup.txt").write_text(
            "AWS_ACCESS_KEY_ID=test-access-key\n"
            "AWS_SECRET_ACCESS_KEY=test-secret-key\n"
            "AWS_S3_HOST=s3.test.com\n"
            "AWS_S3_REGION=us-test-1\n"
            "AWS_S3_BUCKET=test-bucket\n"
        )

        # db_file ("itsup.tar.gz") is written relative to cwd; keep it inside the temp tree.
        os.chdir(self._tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._prev_cwd)
        if self._prev_root is None:
            os.environ.pop("ITSUP_ROOT", None)
        else:
            os.environ["ITSUP_ROOT"] = self._prev_root
        self._tmp.cleanup()

    @mock.patch("boto3.client")
    def test_backup_uploads_upstream_tree(self, mock_boto3_client: mock.MagicMock) -> None:
        s3_client = mock.MagicMock()
        s3_client.list_objects_v2.return_value = {"Contents": []}
        mock_boto3_client.return_value = s3_client

        main()

        # boto3 is configured from the real secrets file resolved under ITSUP_ROOT.
        self.assertEqual(mock_boto3_client.call_count, 1)
        args, kwargs = mock_boto3_client.call_args
        self.assertEqual(args[0], "s3")
        self.assertEqual(kwargs["endpoint_url"], "https://s3.test.com")
        self.assertEqual(kwargs["aws_access_key_id"], "test-access-key")
        self.assertEqual(kwargs["aws_secret_access_key"], "test-secret-key")
        self.assertEqual(kwargs["region_name"], "us-test-1")
        self.assertIsInstance(kwargs["config"], Config)
        self.assertEqual(kwargs["config"].signature_version, "s3v4")

        # The real archive of the upstream tree was uploaded and then cleaned up.
        s3_client.upload_fileobj.assert_called_once()
        self.assertFalse((Path(self._tmp.name) / "itsup.tar.gz").exists())


class TestBackupOrchestration(unittest.TestCase):
    """Real-boundary test: real adapter scripts + real tar, mocked S3.

    Adapters are real project-local shell scripts (no docker) so the test
    exercises concurrent dispatch, derived path-level exclusion, proxy capture,
    and the surfaced partial-availability signal at the real subprocess boundary.
    """

    def setUp(self) -> None:
        self._prev_root = os.environ.get("ITSUP_ROOT")
        self._prev_cwd = os.getcwd()
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
        # DB_FILE ("itsup.tar.gz") is written relative to cwd; keep it in the temp tree.
        os.chdir(self._tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._prev_cwd)
        if self._prev_root is None:
            os.environ.pop("ITSUP_ROOT", None)
        else:
            os.environ["ITSUP_ROOT"] = self._prev_root
        self._tmp.cleanup()

    def _make_upstream_project(self, name: str) -> Path:
        proj = self.root / "upstream" / name
        (proj / "data").mkdir(parents=True)
        (proj / "data" / "live.bin").write_text("torn-live-state")
        return proj

    def _make_adapter_project(self, name: str, *, exclude: list[str], adapter_body: str) -> None:
        """Write projects/<name>/backup.yml + a real project-local adapter script."""
        pdir = self.root / "projects" / name
        pdir.mkdir(parents=True)
        excl = ", ".join(exclude)
        (pdir / "backup.yml").write_text(f"adapter: {name}\nexclude: [{excl}]\n")
        script = pdir / "backup-adapter.sh"
        script.write_text(adapter_body)
        script.chmod(0o755)

    def _run_and_capture_archive(self) -> tuple[list[str], int | None]:
        """Run main(); capture archived member names and any SystemExit code."""
        captured: dict[str, bytes] = {}

        def _capture_upload(fileobj: io.BufferedReader, _bucket: str, _key: str) -> None:
            captured["data"] = fileobj.read()

        exit_code: int | None = None
        with mock.patch("boto3.client") as mock_boto3_client:
            s3_client = mock.MagicMock()
            s3_client.list_objects_v2.return_value = {"Contents": []}
            s3_client.upload_fileobj.side_effect = _capture_upload
            mock_boto3_client.return_value = s3_client
            try:
                main()
            except SystemExit as e:
                exit_code = int(e.code) if e.code is not None else 0
            s3_client.upload_fileobj.assert_called_once()

        with tarfile.open(fileobj=io.BytesIO(captured["data"]), mode="r:gz") as tar:
            names = tar.getnames()
        return names, exit_code

    def test_adapter_dump_included_live_path_excluded(self) -> None:
        """The adapter's _backup/ rides in the archive; the live data dir is pruned."""
        self._make_upstream_project("postgres")
        self._make_adapter_project(
            "postgres",
            exclude=["data"],
            adapter_body=('#!/usr/bin/env sh\nset -eu\nmkdir -p "$2/_backup"\necho dump > "$2/_backup/db.dump"\n'),
        )

        names, exit_code = self._run_and_capture_archive()

        self.assertIn("upstream/postgres/_backup/db.dump", names)
        self.assertNotIn("upstream/postgres/data", names)
        self.assertNotIn("upstream/postgres/data/live.bin", names)
        self.assertIsNone(exit_code)  # clean run does not exit

    def test_proxy_state_in_archive(self) -> None:
        """proxy/ config + certs are captured in the monolithic archive."""
        self._make_upstream_project("web")
        proxy = self.root / "proxy"
        proxy.mkdir()
        (proxy / "acme.json").write_text("{}")

        names, _ = self._run_and_capture_archive()

        self.assertIn("proxy/acme.json", names)

    def test_failing_adapter_is_partial_not_fatal(self) -> None:
        """A failed dump skips that project but still archives the rest, then exits non-zero."""
        self._make_upstream_project("postgres")
        self._make_upstream_project("healthy")
        self._make_adapter_project(
            "postgres",
            exclude=["data"],
            adapter_body='#!/usr/bin/env sh\necho "boom" >&2\nexit 1\n',
        )
        self._make_adapter_project(
            "healthy",
            exclude=["data"],
            adapter_body=('#!/usr/bin/env sh\nset -eu\nmkdir -p "$2/_backup"\necho ok > "$2/_backup/db.dump"\n'),
        )

        names, exit_code = self._run_and_capture_archive()

        # Healthy project's dump is present; the run still uploaded.
        self.assertIn("upstream/healthy/_backup/db.dump", names)
        # The sick project was skipped (no dump), but the run is flagged partial.
        self.assertNotIn("upstream/postgres/_backup/db.dump", names)
        self.assertEqual(exit_code, 1)

    def test_ephemeral_exclude_only_pruned_sibling_kept(self) -> None:
        """An adapter-less backup.yml prunes its data with no dump; a no-config sibling keeps its data."""
        self._make_upstream_project("redis")  # ephemeral store: exclude-only, no adapter
        self._make_upstream_project("web")  # no backup.yml at all
        pdir = self.root / "projects" / "redis"
        pdir.mkdir(parents=True)
        (pdir / "backup.yml").write_text("exclude: [data]\n")  # no adapter, no adapter script

        names, exit_code = self._run_and_capture_archive()

        # redis declares an exclude with no adapter -> its data is pruned without a dump.
        self.assertNotIn("upstream/redis/data/live.bin", names)
        self.assertNotIn("upstream/redis/_backup", names)
        # web has no backup.yml -> its data is archived as-is.
        self.assertIn("upstream/web/data/live.bin", names)
        self.assertIsNone(exit_code)  # no adapter dispatched, clean run

    def test_no_backup_yml_tars_everything(self) -> None:
        """Without any backup.yml, nothing is excluded (legacy itsup.yml field is gone)."""
        self._make_upstream_project("plain")

        names, exit_code = self._run_and_capture_archive()

        # The live data dir is present because no backup.yml declares an exclusion.
        self.assertIn("upstream/plain/data/live.bin", names)
        self.assertIsNone(exit_code)


if __name__ == "__main__":
    unittest.main()
