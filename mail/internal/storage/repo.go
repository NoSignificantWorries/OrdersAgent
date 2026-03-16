package storage

import (
    "fmt"
    "os"
    "path/filepath"
    
    "mail/internal/parser"
)

type Repository interface {
    SaveFile(att parser.Attachment) error
    SaveOrder(order any) error  // Пока any, Order добавим позже
}

// FileRepo — сохранение в папку attachment/
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
    // Заглушка для заказов
    fmt.Println("Заказ сохранен (заглушка)")
    return nil
}
