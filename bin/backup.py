#!/usr/bin/env python3
import os
import sys
import tarfile

import boto3
import botocore.exceptions
from botocore.client import Config
from dotenv import load_dotenv

# Ensure dotenv variables take precedence over existing environment variables
load_dotenv(override=True)


def main() -> None:
    # Configuration
    db_file = "itsup.tar.gz"

    # Check if upstream directory exists
    if not os.path.isdir("./upstream"):
        print("Error: './upstream' directory not found.")
        sys.exit(1)

    # Get exclusions from environment variable
    excluded_folders = []
    backup_exclude = os.environ.get("BACKUP_EXCLUDE", "")
    if backup_exclude:
        excluded_folders = [folder.strip() for folder in backup_exclude.split(",")]

    # Debugging: Print excluded folders
    print(f"Excluded folders: {excluded_folders}")

    # Create tar.gz archive
    print(f"Creating backup archive: {db_file}")
    with tarfile.open(db_file, "w:gz") as tar:
        # Add each file/directory from upstream, skipping excluded folders
        for item in os.listdir("./upstream"):
            item_name = os.path.basename(item)
            if item_name not in excluded_folders:
                item_path = os.path.join("upstream", item)
                print(f"Adding to tarball: {item_path}")
                tar.add(item_path, arcname=item)

    # Use boto3 instead of s3cmd
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    aws_s3_host = os.environ.get("AWS_S3_HOST", "")
    aws_s3_region = os.environ.get("AWS_S3_REGION", "")
    aws_s3_bucket = os.environ.get("AWS_S3_BUCKET", "")

    if not all([aws_access_key, aws_secret_key, aws_s3_host, aws_s3_bucket]):
        print("Error: AWS credentials or configuration missing.")
        sys.exit(1)

    print("Uploading backup to S3")

    # Format endpoint URL correctly
    if not aws_s3_host.startswith(("http://", "https://")):
        endpoint_url = f"https://{aws_s3_host}"
    else:
        endpoint_url = aws_s3_host

    # Debugging: Print AWS S3 configuration
    print(f"AWS S3 Configuration: Host={aws_s3_host}, Region={aws_s3_region}, Bucket={aws_s3_bucket}")

    # Debugging: Print endpoint URL
    print(f"Endpoint URL: {endpoint_url}")

    # Configure boto3 with endpoint URL and credentials
    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_s3_region,
        config=Config(signature_version="s3v4"),
    )

    # List existing versions of the backup file
    print("Checking existing backup versions in S3...")
    existing_versions = []
    response = s3_client.list_objects_v2(Bucket=aws_s3_bucket)
    if "Contents" in response:
        for obj in response["Contents"]:
            existing_versions.append(obj["Key"])
    print(f"Existing versions: {existing_versions}")

    # Rotate existing backups to keep only 10 versions
    from datetime import datetime

    # Generate a timestamped name for the new backup
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    new_backup_name = f"{db_file}.{timestamp}"

    # Sort existing backups by timestamp and delete older ones if more than 10 exist
    backup_prefix = f"{db_file}."
    timestamped_backups = [key for key in existing_versions if key.startswith(backup_prefix)]
    timestamped_backups.sort(reverse=True)

    if len(timestamped_backups) >= 10:
        for old_backup in timestamped_backups[10:]:
            print(f"Deleting old backup: {old_backup}")
            s3_client.delete_object(Bucket=aws_s3_bucket, Key=old_backup)

    # Upload the new backup with the timestamped name
    print(f"Uploading new backup: {new_backup_name}")
    with open(db_file, "rb") as file_data:
        s3_client.upload_fileobj(file_data, aws_s3_bucket, new_backup_name)
    print("Backup completed successfully")

    try:
        # Debugging: List objects in the bucket
        response = s3_client.list_objects_v2(Bucket=aws_s3_bucket)
        if "Contents" in response:
            print("Objects in bucket:")
            for obj in response["Contents"]:
                print(f" - {obj['Key']}")
        else:
            print("Bucket is empty.")
    except botocore.exceptions.ClientError as e:
        print(f"Error listing objects in bucket: {e}")

    except botocore.exceptions.ClientError as e:
        print(f"AWS S3 Client Error: {e}")
        sys.exit(1)
    except botocore.exceptions.EndpointConnectionError as e:
        print(f"Cannot connect to endpoint {endpoint_url}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        sys.exit(1)
    finally:
        # Optionally clean up the local backup file after upload
        os.remove(db_file)
        pass


if __name__ == "__main__":
    main()
