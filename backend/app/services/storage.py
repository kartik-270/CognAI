import os
import shutil
import uuid
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseStorageService(ABC):
    @abstractmethod
    async def save_file(self, user_id: str, session_id: str, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        """Saves file and returns metadata dictionary."""
        pass

    @abstractmethod
    async def get_file_bytes(self, storage_path: str) -> bytes:
        """Retrieves raw file bytes."""
        pass

    @abstractmethod
    async def delete_file(self, storage_path: str) -> bool:
        """Deletes a single file."""
        pass

    @abstractmethod
    async def delete_user_files(self, user_id: str) -> bool:
        """Purges all files belonging to user for cascading delete /forget-me compliance."""
        pass


class LocalStorageService(BaseStorageService):
    """
    Local file storage isolating files under storage/attachments/{user_id}/{session_id}/.
    Designed for zero-friction future migration to AWS S3.
    """
    def __init__(self, base_dir: str = "storage/attachments"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    async def save_file(self, user_id: str, session_id: str, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        file_id = str(uuid.uuid4())
        # Sanitize filename
        safe_name = os.path.basename(file_name).replace(" ", "_")
        target_dir = os.path.join(self.base_dir, user_id, session_id)
        os.makedirs(target_dir, exist_ok=True)
        
        target_path = os.path.join(target_dir, f"{file_id}_{safe_name}")
        with open(target_path, "wb") as f:
            f.write(file_bytes)

        return {
            "file_id": file_id,
            "storage_path": target_path,
            "file_size": len(file_bytes),
            "file_name": safe_name
        }

    async def get_file_bytes(self, storage_path: str) -> bytes:
        if not os.path.exists(storage_path):
            raise FileNotFoundError(f"File not found at {storage_path}")
        with open(storage_path, "rb") as f:
            return f.read()

    async def delete_file(self, storage_path: str) -> bool:
        try:
            if os.path.exists(storage_path):
                os.remove(storage_path)
                return True
        except Exception as e:
            logger.warning(f"Failed to delete file {storage_path}: {e}")
        return False

    async def delete_user_files(self, user_id: str) -> bool:
        user_dir = os.path.join(self.base_dir, user_id)
        if os.path.exists(user_dir):
            try:
                shutil.rmtree(user_dir)
                logger.info(f"Purged all local attachments for user {user_id}")
                return True
            except Exception as e:
                logger.warning(f"Error purging attachments for user {user_id}: {e}")
        return False


class S3StorageService(BaseStorageService):
    """
    AWS S3 implementation stub. Ready for S3 bucket activation.
    """
    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or os.environ.get("S3_ATTACHMENTS_BUCKET", "cognai-attachments")

    async def save_file(self, user_id: str, session_id: str, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        file_id = str(uuid.uuid4())
        safe_name = os.path.basename(file_name).replace(" ", "_")
        s3_key = f"attachments/{user_id}/{session_id}/{file_id}_{safe_name}"
        
        import boto3
        s3 = boto3.client("s3")
        s3.put_object(Bucket=self.bucket_name, Key=s3_key, Body=file_bytes)
        
        return {
            "file_id": file_id,
            "storage_path": f"s3://{self.bucket_name}/{s3_key}",
            "file_size": len(file_bytes),
            "file_name": safe_name
        }

    async def get_file_bytes(self, storage_path: str) -> bytes:
        import boto3
        s3 = boto3.client("s3")
        # Parse s3://bucket/key
        key = storage_path.replace(f"s3://{self.bucket_name}/", "")
        obj = s3.get_object(Bucket=self.bucket_name, Key=key)
        return obj["Body"].read()

    async def delete_file(self, storage_path: str) -> bool:
        import boto3
        s3 = boto3.client("s3")
        key = storage_path.replace(f"s3://{self.bucket_name}/", "")
        s3.delete_object(Bucket=self.bucket_name, Key=key)
        return True

    async def delete_user_files(self, user_id: str) -> bool:
        import boto3
        s3 = boto3.client("s3")
        prefix = f"attachments/{user_id}/"
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            if "Contents" in page:
                delete_keys = [{'Key': obj['Key']} for obj in page['Contents']]
                s3.delete_objects(Bucket=self.bucket_name, Delete={'Objects': delete_keys})
        return True


def get_storage_service() -> BaseStorageService:
    # Defaults to local storage for now, easily toggled to S3 via USE_S3_STORAGE=true
    if os.environ.get("USE_S3_STORAGE", "false").lower() == "true":
        return S3StorageService()
    return LocalStorageService()
