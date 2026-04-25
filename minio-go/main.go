package main

import (
	"context"
	"fmt"
	"log"
	"strings"

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
		return nil, fmt.Errorf("Connection lost: %w", err)
	}

	return &CloudStorage{
		client: client,
		bucket: bucket,
	}, nil
}

func (s *CloudStorage) CreateFolder(ctx context.Context, folderPath string) error {
	key := strings.TrimSuffix(folderPath, "/") + "/"

	_, err := s.client.PutObject(ctx, s.bucket, key, strings.NewReader(""), 0, minio.PutObjectOptions{})
	if err != nil {
		return fmt.Errorf("Folder does not created %s: %w", folderPath, err)
	}

	log.Printf("Folder created: %s", key)
	return nil
}

func (s *CloudStorage) UploadFile(ctx context.Context, localPath, cloudPath string, data []byte) error {
	reader := strings.NewReader(string(data))

	_, err := s.client.PutObject(ctx, s.bucket, cloudPath, reader, int64(len(data)), minio.PutObjectOptions{
		ContentType: "application/octet-stream",
	})
	if err != nil {
		return fmt.Errorf("File not loaded: %w", err)
	}

	log.Printf("File loaded: %s -> %s (%d byte)", localPath, cloudPath, len(data))
	return nil
}

func (s *CloudStorage) DownloadFile(ctx context.Context, cloudPath string) ([]byte, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, cloudPath, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("Error with file downloading: %w", err)
	}
	defer obj.Close()

	stat, err := obj.Stat()
	if err != nil {
		return nil, fmt.Errorf("Error reading statistic: %w", err)
	}

	data := make([]byte, stat.Size)
	_, err = obj.Read(data)
	if err != nil {
		return nil, fmt.Errorf("Data reading error: %w", err)
	}

	log.Printf("File downloaded: %s (size: %d byte)", cloudPath, stat.Size)
	return data, nil
}

func (s *CloudStorage) DeleteFolder(ctx context.Context, folderPath string) error {
	prefix := strings.TrimSuffix(folderPath, "/") + "/"

	objectsCh := s.client.ListObjects(ctx, s.bucket, minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	})

	var objectsToDelete []minio.ObjectInfo
	for obj := range objectsCh {
		if obj.Err != nil {
			return fmt.Errorf("Listing error: %w", obj.Err)
		}
		objectsToDelete = append(objectsToDelete, obj)
	}

	if len(objectsToDelete) == 0 {
		log.Printf("Folder empty or not exists: %s", folderPath)
		return nil
	}

	for _, obj := range objectsToDelete {
		err := s.client.RemoveObject(ctx, s.bucket, obj.Key, minio.RemoveObjectOptions{})
		if err != nil {
			log.Printf("Deleting error %s: %v", obj.Key, err)
		} else {
			log.Printf("Deleted: %s", obj.Key)
		}
	}

	log.Printf("Folder deleted: %s (deleted objects: %d)", folderPath, len(objectsToDelete))
	return nil
}

func (s *CloudStorage) DeleteFolderBatch(ctx context.Context, folderPath string) error {
	prefix := strings.TrimSuffix(folderPath, "/") + "/"

	objectsCh := s.client.ListObjects(ctx, s.bucket, minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	})

	var objects []minio.ObjectInfo
	for obj := range objectsCh {
		objects = append(objects, obj)
	}

	objectsToRemove := make(chan minio.ObjectInfo, len(objects))
	for _, obj := range objects {
		objectsToRemove <- obj
	}
	close(objectsToRemove)

	for obj := range objectsToRemove {
		if err := s.client.RemoveObject(ctx, s.bucket, obj.Key, minio.RemoveObjectOptions{}); err != nil {
			log.Printf("Deleting error %s: %v", obj.Key, err)
		}
	}

	return nil
}

func (s *CloudStorage) DeleteFile(ctx context.Context, cloudPath string) error {
	err := s.client.RemoveObject(ctx, s.bucket, cloudPath, minio.RemoveObjectOptions{})
	if err != nil {
		return fmt.Errorf("Deleting file error: %w", err)
	}

	log.Printf("File deleted: %s", cloudPath)
	return nil
}

func (s *CloudStorage) EnsureFolder(ctx context.Context, folderPath string) error {
	prefix := strings.TrimSuffix(folderPath, "/") + "/"

	objects := s.client.ListObjects(ctx, s.bucket, minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: false,
		MaxKeys:   1,
	})

	for range objects {
		log.Printf("Folder exists: %s", folderPath)
		return nil
	}

	return s.CreateFolder(ctx, folderPath)
}

func main() {
	ctx := context.Background()

	storage, err := NewCloudStorage(
		"localhost:9000",     // endpoint
		"minioadmin",         // accessKeyID
		"minioadmin",         // secretAccessKey
		"orders-attachments", // bucket name
		false,                // useSSL (false для локального MinIO)
	)
	if err != nil {
		log.Fatal(err)
	}

	exists, err := storage.client.BucketExists(ctx, storage.bucket)
	if err != nil {
		log.Fatal(err)
	}
	if !exists {
		log.Fatalf("Бакет %s не существует! Создайте его в MinIO", storage.bucket)
	}

	// 1. СОЗДАНИЕ ПАПКИ
	err = storage.CreateFolder(ctx, "projects/2024/reports")
	if err != nil {
		log.Printf("Ошибка: %v", err)
	}

	// 2. ЗАГРУЗКА ФАЙЛА (ЗАПИСЬ)
	fileContent := []byte("Это содержимое моего файла\nВторая строка")
	err = storage.UploadFile(ctx, "local.txt", "projects/2024/reports/result.txt", fileContent)
	if err != nil {
		log.Printf("Ошибка: %v", err)
	}

	// 3. ЧТЕНИЕ ФАЙЛА
	data, err := storage.DownloadFile(ctx, "projects/2024/reports/result.txt")
	if err != nil {
		log.Printf("Ошибка: %v", err)
	} else {
		fmt.Printf("Содержимое файла:\n%s\n", string(data))
	}

	// 4. ДОБАВЛЕНИЕ ПАПКИ (только если не существует)
	err = storage.EnsureFolder(ctx, "projects/2024/backups")
	if err != nil {
		log.Printf("Ошибка: %v", err)
	}

	// 5. УДАЛЕНИЕ ОДНОГО ФАЙЛА
	err = storage.DeleteFile(ctx, "projects/2024/reports/result.txt")
	if err != nil {
		log.Printf("Ошибка: %v", err)
	}

	// 6. УДАЛЕНИЕ ПАПКИ (рекурсивно)
	err = storage.DeleteFolder(ctx, "projects/2024")
	if err != nil {
		log.Printf("Ошибка: %v", err)
	}

	fmt.Println("\n🎉 Все операции завершены!")
}
