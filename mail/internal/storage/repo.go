package storage

import (
    "context"
    "fmt"
    "os"
    "time"

    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/storage/api"
    minio "worker/minio/minio"
    //"OrdersAgent/temporal/client/launcher"
)

// Repository — общий интерфейс
type Repository interface {
    SaveFile(att parser.Attachment) error
    SaveOrder(userID int64, order any) error
}

// FileRepo — старая файловая реализация (если больше не нужна, можно удалить целиком)
type FileRepo struct{}

func NewFileRepo() Repository {
    return &FileRepo{}
}

func (f *FileRepo) SaveFile(att parser.Attachment) error {
    // больше не используется
    return fmt.Errorf("FileRepo.SaveFile is deprecated")
}

func (f *FileRepo) SaveOrder(userID int64, order any) error {
    // заглушка
    return nil
}

// DBRepo — пишет метаданные в Postgres и файлы в MinIO
type DBRepo struct {
    db    *api.DB
    store *minio.CloudStorage
}

// NewDBRepo принимает и БД, и объектное хранилище
func NewDBRepo(db *api.DB, store *minio.CloudStorage) Repository {
    return &DBRepo{
        db:    db,
        store: store,
    }
}

// SaveFile сейчас не используется, всё делаем через SaveOrder
func (r *DBRepo) SaveFile(att parser.Attachment) error {
    // намеренно ничего не делаем
    return nil
}

func (r *DBRepo) SaveOrder(userID int64, order any) error {
    email, ok := order.(*parser.Email)
    if !ok {
        return fmt.Errorf("SaveOrder: expected *parser.Email, got %T", order)
    }

    ctx := context.Background()
    managerID := int64(1)
    emailUID := int64(email.UID)

    var emailFrom *string
    if email.From != "" {
        from := email.From
        emailFrom = &from
    }

    var emailDate *time.Time
    if email.Date != "" {
        if parsed, err := time.Parse("2006-01-02 15:04", email.Date); err == nil {
            emailDate = &parsed
        }
    }

    bucket := os.Getenv("MINIO_BUCKET")
    if bucket == "" {
        bucket = "orders-attachments"
    }

    if len(email.Files) > 0 {
        for i, f := range email.Files {
            name := f.Name

            // object key по схеме {email_uid}/{index}_{filename}
            objectKey := fmt.Sprintf("%d/%d_%s", emailUID, i+1, name)

            // 1. грузим файл в MinIO
            if err := r.store.Upload(ctx, objectKey, f.Data); err != nil {
                return fmt.Errorf("upload attachment %s (key=%s): %w", name, objectKey, err)
            }

            // 2. пишем строку в process_queue
            item := api.QueueItem{
                AssignedTo:   &managerID,
                TargetUserID: userID,
                Subject:      email.Subject,
                Body:         email.Body,
                EmailUID:     &emailUID,
                EmailFrom:    emailFrom,
                EmailDate:    emailDate,
                DocName:      &name,
                ObjectBucket: &bucket,
                ObjectKey:    &objectKey,
                Status:       "wait",
            }

            _, err := r.db.InsertQueueItem(ctx, item)
            if err != nil {
                return fmt.Errorf("insert queue item (uid=%d, key=%s): %w", emailUID, objectKey, err)
            }

            // workflowID, runID, err := launcher.StartProcessQueueWorkflow(ctx, queueID, item.TargetUserID)
            // if err != nil {
            //     return fmt.Errorf("start workflow for queue item %d (uid=%d, key=%s): %w", queueID, emailUID, objectKey, err)
            // }

            // fmt.Printf("queue item created id=%d, workflow started workflowID=%s runID=%s\n", queueID, workflowID, runID)
        }
        return nil
    }

    // если вложений нет — одна запись без document_name/object_key
    item := api.QueueItem{
        AssignedTo:   &managerID,
        TargetUserID: userID,
        Subject:      email.Subject,
        Body:         email.Body,
        EmailUID:     &emailUID,
        EmailFrom:    emailFrom,
        EmailDate:    emailDate,
        DocName:      nil,
        ObjectBucket: nil,
        ObjectKey:    nil,
        Status:       "wait",
    }

    _, err := r.db.InsertQueueItem(ctx, item)
    if err != nil {
        return fmt.Errorf("insert queue item (uid=%d, no attachments): %w", emailUID, err)
    }

    // workflowID, runID, err := launcher.StartProcessQueueWorkflow(ctx, queueID, item.TargetUserID)
    // if err != nil {
    //     return fmt.Errorf("start workflow for queue item %d (uid=%d, no attachments): %w", queueID, emailUID, err)
    // }

    // fmt.Printf("queue item created id=%d, workflow started workflowID=%s runID=%s\n", queueID, workflowID, runID)

    return nil
}