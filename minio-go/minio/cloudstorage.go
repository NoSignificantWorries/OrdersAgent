package minio

import (
    "bytes"
    "context"
    "fmt"
    "io"

    "github.com/minio/minio-go/v7"
    "github.com/minio/minio-go/v7/pkg/credentials"
)

type CloudStorage struct {
    client *minio.Client
    bucket string
}

func NewCloudStorage(endpoint, accessKey, secretKey, bucket string, useSSL bool) (*CloudStorage, error) {
    client, err := minio.New(endpoint, &minio.Options{
        Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
        Secure: useSSL,
    })
    if err != nil {
        return nil, fmt.Errorf("connect to MinIO: %w", err)
    }

    return &CloudStorage{
        client: client,
        bucket: bucket,
    }, nil
}

func (s *CloudStorage) Upload(ctx context.Context, objectKey string, data []byte) error {
    reader := bytes.NewReader(data)

    _, err := s.client.PutObject(ctx, s.bucket, objectKey, reader, int64(len(data)), minio.PutObjectOptions{
        ContentType: "application/octet-stream",
    })
    if err != nil {
        return fmt.Errorf("upload object %s: %w", objectKey, err)
    }

    return nil
}

func (s *CloudStorage) Download(ctx context.Context, objectKey string) ([]byte, error) {
    obj, err := s.client.GetObject(ctx, s.bucket, objectKey, minio.GetObjectOptions{})
    if err != nil {
        return nil, fmt.Errorf("get object %s: %w", objectKey, err)
    }
    defer obj.Close()

    data, err := io.ReadAll(obj)
    if err != nil {
        return nil, fmt.Errorf("read object %s: %w", objectKey, err)
    }

    return data, nil
}