package storage

import (
    "fmt"
    "os"
    "path/filepath"
    "context"

    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/storage/api"
)

type Repository interface {
    SaveFile(att parser.Attachment) error
    SaveOrder(order any) error
}

// Файловая реализация (старая).
type FileRepo struct{}

func NewFileRepo() Repository {
    return &FileRepo{}
}

func (f *FileRepo) SaveFile(att parser.Attachment) error {
    dir := "attachment"
    if err := os.MkdirAll(dir, 0755); err != nil {
        return fmt.Errorf("create dir %s: %w", dir, err)
    }

    fullPath := filepath.Join(dir, att.Name)
    if err := os.WriteFile(fullPath, att.Data, 0644); err != nil {
        return fmt.Errorf("save %s: %w", att.Name, err)
    }

    fmt.Printf("Сохранено: %s (%d байт)\n", fullPath, len(att.Data))
    return nil
}

func (f *FileRepo) SaveOrder(order any) error {
    fmt.Println("Заказ сохранен (заглушка, FileRepo)")
    return nil
}

// DBRepo — реализация Repository, которая пишет в Postgres
type DBRepo struct {
    db *api.DB
}

func NewDBRepo(db *api.DB) Repository {
    return &DBRepo{db: db}
}

func (r *DBRepo) SaveFile(att parser.Attachment) error {
    // пока вложения сохраняем только через SaveOrder (не сохраняем)
    fmt.Printf("SaveFile: %s (пока игнорируем)\n", att.Name)
    return nil
}

func (r *DBRepo) SaveOrder(order any) error {
    email, ok := order.(*parser.Email)
    if !ok {
        return fmt.Errorf("expected *parser.Email, got %T", order)
    }

    ctx := context.Background()
    managerID := int64(1)
    emailUID := int64(email.UID)

    // по заявке на каждый
    if len(email.Files) > 0 {
        for _, f := range email.Files {
            name := f.Name
            item := api.QueueItem{
                AssignedTo: &managerID,
                Subject: email.Subject,
                Body: email.Body,
                EmailUID:   &emailUID,
                DocName: &name,
                DocData: f.Data,
                Status: "wait",
            }
            if err := r.db.InsertQueueItem(ctx, item); err != nil {
                return err
            }
        }
        return nil
    }
    item := api.QueueItem{
                AssignedTo: &managerID,
                Subject: email.Subject,
                Body: email.Body,
                EmailUID:   &emailUID,
                DocName: nil,
                DocData: nil,
                Status: "wait",
            }
    // если файлов нет - заявка без document_name
    return r.db.InsertQueueItem(ctx, item)
}
