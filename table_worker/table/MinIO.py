import os
from typing import Optional

from minio import Minio
from minio.error import S3Error


class MinIOClient:
    _instance: Optional[Minio] = None

    @classmethod
    def get_client(cls) -> Minio:
        if cls._instance is None:
            cls._instance = Minio(
                "localhost:9000",
                access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
                secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
                secure=False
            )
        return cls._instance


def development():
    bucket_name = "orders-attachments"

    client = MinIOClient().get_client()

    print(client)

    response = client.get_object("orders-attachments", "test.txt")

    print(response)


if __name__ == "__main__":
    development()

