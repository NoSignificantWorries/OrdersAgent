import os
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error


class MinIOClient:
    _instance: Optional[Minio] = None

    @classmethod
    def get_client(cls) -> Minio:
        if cls._instance is None:
            cls._instance = Minio(
                os.getenv("MINIO_ENDPOINT", "localhost:9000"),
                access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
                secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
                secure=False,
            )
        return cls._instance


def get_bytes_object(client: Minio, bucket: str, filename: str) -> Optional[BytesIO]:
    try:
        response = client.get_object(bucket, filename)
        file_data = BytesIO(response.read())
        response.close()
        response.release_conn()
        return file_data
    except Exception:
        print("Errors while file reading")
        return None


def put_bytes_object(
    client: Minio, bucket: str, filename: str, data: BytesIO, content_type: str
) -> bool:
    try:
        client.put_object(
            bucket_name=bucket,
            object_name=filename,
            data=data,
            length=data.getbuffer().nbytes,
            content_type=content_type,
        )
        return False
    except Exception:
        print("Error while saving file in the cloud")
        return True


def development() -> None:
    bucket_name = "orders-attachments"

    client = MinIOClient().get_client()

    print(client)

    response = client.get_object("orders-attachments", "test.txt")

    print(response)


if __name__ == "__main__":
    development()
