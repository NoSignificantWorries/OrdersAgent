package storage

import (
    "fmt"
    "os"
    "path/filepath"

    "OrdersAgent/mail/internal/parser"
)

type DatasetRepo struct {
    Dir string
}

func NewDatasetRepo(dir string) *DatasetRepo {
    return &DatasetRepo{Dir: dir}
}

func (r *DatasetRepo) SaveFile(att parser.Attachment) error {
    fmt.Printf("DatasetRepo.SaveFile: %s (игнорируем для датасета)\n", att.Name)
    return nil
}

func (r *DatasetRepo) SaveOrder(order any) error {
    email, ok := order.(*parser.Email)
    if !ok {
        return fmt.Errorf("expected *parser.Email, got %T", order)
    }

    if err := os.MkdirAll(r.Dir, 0755); err != nil {
        return fmt.Errorf("create dir %s: %w", r.Dir, err)
    }

    // Имя файла: по UID письма
    fileName := fmt.Sprintf("email_%d.txt", email.UID)
    fullPath := filepath.Join(r.Dir, fileName)

    content := email.Subject + "\n"

    for i, f := range email.Files {
        content += fmt.Sprintf("FILE_%d: %s\n", i+1, f.Name)
    }

    content += "\n" + email.Body + "\n"

    if err := os.WriteFile(fullPath, []byte(content), 0644); err != nil {
        return fmt.Errorf("write dataset file: %w", err)
    }

    fmt.Printf("Dataset saved: %s\n", fullPath)
    return nil
}
