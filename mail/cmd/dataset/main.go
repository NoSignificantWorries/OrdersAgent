package main

import (
    "fmt"
    "log"
    "os"
    "os/signal"
    "syscall"
    "time"

    "OrdersAgent/mail/internal/client"
    "OrdersAgent/mail/internal/config"
    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/mail/internal/orders"
    "OrdersAgent/mail/internal/storage"
)

func main() {	
    fmt.Printf("OrdersAgent dataset builder\n")
    cfg, err := config.Load("mail/internal/config/config.json")
    if err != nil {
        log.Fatalf("config: %v", err)
    }

    fmt.Printf("OrdersAgent dataset builder start\n")
    fmt.Printf("%s:%d | %s\n", cfg.Host, cfg.Port, cfg.Username)

    imapClient, err := client.New(cfg)
    if err != nil {
        log.Fatalf("IMAP client: %v", err)
    }
    defer imapClient.Close()

    repo := storage.NewDatasetRepo("dataset_emails")
    processor := orders.New(repo)

    c := make(chan os.Signal, 1)
    signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)

    fmt.Println("\nСбор датасета...")
    ProcessEmailsOnce(imapClient, c, processor)
}

func ProcessEmailsOnce(imap *client.Client, sigChan chan os.Signal, processor *orders.Processor) {
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

        time.Sleep(100 * time.Millisecond)
    }
}
