package main

import (
    "fmt"
    "log"
    "os"
    "os/signal"
    "syscall"
    "time"
    
    "mail/internal/client"
    "mail/internal/config"
    "mail/internal/parser"
    "mail/internal/orders"
    "mail/internal/storage"
)

func main() {
    cfg, err := config.Load("internal/config/config.json")
    if err != nil {
        log.Fatalf("config: %v", err)
    }
    
    fmt.Printf("OrdersAgent v1.0\n")
    fmt.Printf("%s:%d | %s\n", cfg.Host, cfg.Port, cfg.Username)
    
    imapClient, err := client.New(cfg)
    if err != nil {
        log.Fatalf("IMAP client: %v", err)
    }
    defer imapClient.Close()
    
    repo := &storage.FileRepo{}
    processor := orders.New(repo)

    ticker := time.NewTicker(10 * time.Second)
    defer ticker.Stop()
    
    c := make(chan os.Signal, 1)
    signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)
    
    for {
        select {
        case <-ticker.C:
            fmt.Println("\nПроверка почты...")
            ProcessEmails(imapClient, c, processor)
        case <-c:
            fmt.Printf("\nОстановка...")
            return
        }
    }
}

func ProcessEmails(imap *client.Client, sigChan chan os.Signal, processor *orders.Processor) {
    uids, err := imap.FetchUnread()
    if err != nil {
        log.Printf("fetch unread: %v", err)
        return
    }
    
    if len(uids) == 0 {
        fmt.Println("No new emails")
        return
    }
    
    for _, uid := range uids {
        select {
        case <-sigChan:
            fmt.Println("Прерывание...")
            return
        default:
        }

        fmt.Printf("Processing UID: %d\n", uid)
        
        fetchCmd, err := imap.FetchMessage(uid)
        if err != nil {
            log.Printf("fetch message: %v", err)
            continue
        }
        
        email, err := parser.ParseMessage(uid, fetchCmd)
        if err != nil {
            log.Printf("parse: %v", err)
            fetchCmd.Close()
            continue
        }
        
        if err := processor.ProcessEmail(email); err != nil {
            log.Printf("process email: %v", err)
        }
        
        fetchCmd.Close()
        imap.MarkRead(uid)
    }
}
