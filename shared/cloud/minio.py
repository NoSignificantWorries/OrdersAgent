import os
from io import BytesIO
from typing import Optional

import anyio.to_thread
from minio import Minio
from minio.error import S3Error


class AsyncMinIOClient:
    _instance: Optional[Minio] = None

    @classmethod
    def _get_sync_client(cls) -> Minio:
        if cls._instance is None:
            cls._instance = Minio(
                os.getenv("MINIO_ENDPOINT", "localhost:9000"),
                access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
                secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
                secure=False,
            )
        return cls._instance

    @classmethod
    async def get_object(cls, bucket: str, filename: str) -> Optional[BytesIO]:
        client = cls._get_sync_client()

        try:
            response = await anyio.to_thread.run_sync(
                client.get_object, bucket, filename
            )
            data = response.read()
            response.close()
            response.release_conn()
            return BytesIO(data)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            return None

    @classmethod
    async def put_object(
        cls,
        bucket: str,
        filename: str,
        data: BytesIO,
        content_type: str = "application/octet-stream",
    ) -> bool:
        client = cls._get_sync_client()

        try:
            data.seek(0)
            await anyio.to_thread.run_sync(
                client.put_object,
                bucket,
                filename,
                data,
                data.getbuffer().nbytes,
                content_type=content_type,
            )
            return True
        except Exception as e:
            print(f"Error uploading {filename}: {e}")
            return False

    @classmethod
    async def file_exists(cls, bucket: str, filename: str) -> bool:
        client = cls._get_sync_client()

        try:
            await anyio.to_thread.run_sync(client.stat_object, bucket, filename)
            return True
        except Exception:
            return False


async def main():
    bucket = "orders-attachments"
    data = BytesIO(b"Hello async world!")

    success = await AsyncMinIOClient.put_object(bucket, "test.txt", data)
    print(f"Upload: {success}")

    file_data = await AsyncMinIOClient.get_object(bucket, "test.txt")
    if file_data:
        print(file_data.read().decode())


# import os
# from io import BytesIO
# from typing import Optional

# from minio import Minio
# from minio.error import S3Error


# class MinIOClient:
#     _instance: Optional[Minio] = None

#     @classmethod
#     def get_client(cls) -> Minio:
#         if cls._instance is None:
#             cls._instance = Minio(
#                 os.getenv("MINIO_ENDPOINT", "localhost:9000"),
#                 access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
#                 secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
#                 secure=False,
#             )
#         return cls._instance


# def get_bytes_object(client: Minio, bucket: str, filename: str) -> Optional[BytesIO]:
#     try:
#         response = client.get_object(bucket, filename)
#         file_data = BytesIO(response.read())
#         response.close()
#         response.release_conn()
#         return file_data
#     except Exception:
#         print("Errors while file reading")
#         return None


# def put_bytes_object(
#     client: Minio, bucket: str, filename: str, data: BytesIO, content_type: str
# ) -> bool:
#     try:
#         client.put_object(
#             bucket_name=bucket,
#             object_name=filename,
#             data=data,
#             length=data.getbuffer().nbytes,
#             content_type=content_type,
#         )
#         return False
#     except Exception:
#         print("Error while saving file in the cloud")
#         return True


# def development() -> None:
#     bucket_name = "orders-attachments"

#     client = MinIOClient().get_client()

#     print(client)

#     response = client.get_object("orders-attachments", "test.txt")

#     print(response)


# if __name__ == "__main__":
#     development()
