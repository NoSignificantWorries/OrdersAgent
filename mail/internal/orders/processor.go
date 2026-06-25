package orders

import (
    "fmt"
    "os"
    "path/filepath"
    
    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/mail/internal/storage"
)

type Processor struct {
    repo storage.Repository
}

func New(repo storage.Repository) *Processor {
    return &Processor{repo: repo}
}

func (p *Processor) ProcessEmail(email *parser.Email) error {
    fmt.Printf("   От: %s\n", email.From)
    fmt.Printf("   Тема: %s\n", email.Subject)
    fmt.Printf("   Дата: %s\n", email.Date)
    fmt.Printf("   Тело: %s\n", email.Body)
    fmt.Printf("    UID: %s\n", email.UID)
    
    for _, file := range email.Files {
        if err := p.repo.SaveFile(file); err != nil {
            fmt.Printf("%s: %v\n", file.Name, err)
            continue
        }
    }

    if err := p.repo.SaveOrder(email); err != nil {
        return err
    }
    
    fmt.Println("---")
    return nil
}

func (p *Processor) saveAttachment(file parser.Attachment) error {
    dir := "attachment"
    if err := os.MkdirAll(dir, 0755); err != nil {
        return fmt.Errorf("create dir: %w", err)
    }
    
    fullPath := filepath.Join(dir, file.Name)
    
    if err := os.WriteFile(fullPath, file.Data, 0644); err != nil {
        return fmt.Errorf("write file: %w", err)
    }
    
    return nil
}
