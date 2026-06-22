import os
import sys
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


if __name__ == "__main__":
    unittest.main()
