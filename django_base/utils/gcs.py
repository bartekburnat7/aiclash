from django.core.files.uploadedfile import UploadedFile
from django.core.exceptions import ValidationError
from google.cloud import storage
from google.oauth2 import service_account
from google.cloud.exceptions import NotFound
import os
import json

# Initialize GCS client
service_account_info = json.loads(os.environ["storage_service_account"])
credentials = service_account.Credentials.from_service_account_info(service_account_info)
client = storage.Client(credentials=credentials, project=service_account_info["project_id"])


def upload_file(bucket_name: str, blob_path: str, file_obj: UploadedFile, make_public: bool = False):
    """
    Upload a file to Google Cloud Storage.

    Args:
        bucket_name (str): The name of the GCS bucket.
        blob_path (str): The path/key for the object in the bucket.
        file_obj (UploadedFile): The file object to upload.
        make_public (bool): Whether to make the file publicly accessible.

    Returns:
        dict: Metadata about the uploaded file including blob_path, size, content_type, and public_url if made public.
    """
    try:
        file_obj.seek(0)
    except Exception:
        pass

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if make_public:
        blob.upload_from_file(
            file_obj,
            content_type=getattr(file_obj, "content_type", None),
            predefined_acl="publicRead",
        )
    else:
        blob.upload_from_file(
            file_obj,
            content_type=getattr(file_obj, "content_type", None),
        )

    return {
        "blob_path": blob_path,
        "size": getattr(file_obj, "size", 0),
        "content_type": getattr(file_obj, "content_type", None),
        "public_url": blob.public_url if make_public else None,
    }


def delete_file(bucket_name: str, blob_path: str):
    """
    Delete a file from Google Cloud Storage.

    Args:
        bucket_name (str): The name of the GCS bucket.
        blob_path (str): The path/key of the object to delete.

    Raises:
        ValidationError: If deletion fails.
    """
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.delete()
    except NotFound:
        # File not found, consider it deleted
        pass
    except Exception as e:
        raise ValidationError(f"Failed to delete file {blob_path} from bucket {bucket_name}: {str(e)}")


def get_file_url(bucket_name: str, blob_path: str, make_public: bool = False):
    """
    Get the public URL of a file in GCS. If not public, can make it public.

    Args:
        bucket_name (str): The name of the GCS bucket.
        blob_path (str): The path/key of the object.
        make_public (bool): Whether to make the file public if it's not already.

    Returns:
        str: The public URL of the file.
    """
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    if make_public:
        blob.make_public()
    return blob.public_url


def file_exists(bucket_name: str, blob_path: str):
    """
    Check if a file exists in GCS.

    Args:
        bucket_name (str): The name of the GCS bucket.
        blob_path (str): The path/key of the object.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.exists()
