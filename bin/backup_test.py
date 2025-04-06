import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import os
import unittest
from unittest.mock import MagicMock, call, patch

from backup import main
from botocore.config import Config


class TestBackupScript(unittest.TestCase):

    @patch("os.path.isdir")
    @patch("os.listdir")
    @patch("tarfile.open")
    @patch("boto3.client")
    @patch("os.environ.get")
    def test_backup_script(
        self,
        mock_env_get: MagicMock,
        mock_boto3_client: MagicMock,
        mock_tarfile_open: MagicMock,
        mock_listdir: MagicMock,
        mock_isdir: MagicMock,
    ) -> None:
        # Mock environment variables
        mock_env_get.side_effect = lambda key, default=None: {
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_S3_HOST": "s3.test.com",
            "AWS_S3_REGION": "us-test-1",
            "AWS_S3_BUCKET": "test-bucket",
            "BACKUP_EXCLUDE": "exclude-folder",
        }.get(key, default)

        # Mock os.path.isdir to return True
        mock_isdir.return_value = True

        # Mock os.listdir to return a list of files and folders
        mock_listdir.return_value = ["file1.txt", "file2.txt", "exclude-folder"]

        # Mock tarfile.open to simulate tarball creation
        mock_tar = MagicMock()
        mock_tarfile_open.return_value.__enter__.return_value = mock_tar

        # Mock boto3 S3 client
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client

        # Mock S3 list_objects_v2 response
        mock_s3_client.list_objects_v2.return_value = {"Contents": []}

        # Run the backup script
        with patch("builtins.open", MagicMock()):
            with patch("os.remove") as mock_remove:
                main()

        # Assertions
        mock_isdir.assert_called_once_with("./upstream")
        mock_listdir.assert_called_once_with("./upstream")
        mock_tar.add.assert_any_call(os.path.join("upstream", "file1.txt"), arcname="file1.txt")
        mock_tar.add.assert_any_call(os.path.join("upstream", "file2.txt"), arcname="file2.txt")
        self.assertNotIn("exclude-folder", [call[0][0] for call in mock_tar.add.call_args_list])

        # Instead of directly comparing the Config objects, verify boto3.client was called
        # with the correct parameters
        self.assertEqual(mock_boto3_client.call_count, 1)
        args, kwargs = mock_boto3_client.call_args
        self.assertEqual(args[0], "s3")
        self.assertEqual(kwargs["endpoint_url"], "https://s3.test.com")
        self.assertEqual(kwargs["aws_access_key_id"], "test-access-key")
        self.assertEqual(kwargs["aws_secret_access_key"], "test-secret-key")
        self.assertEqual(kwargs["region_name"], "us-test-1")
        # Verify the Config object has the correct signature_version
        self.assertTrue(isinstance(kwargs["config"], Config))
        self.assertEqual(kwargs["config"].signature_version, "s3v4")

        mock_s3_client.upload_fileobj.assert_called_once()
        mock_remove.assert_called_once_with("itsup.tar.gz")


if __name__ == "__main__":
    unittest.main()
