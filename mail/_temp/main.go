// mail/cmd/mail-agent/main.go
package main

import (
    "flag"
    "log"
    "os"
    "os/signal"
    "syscall"
    "time"

    "github.com/joho/godotenv"

    "OrdersAgent/mail/internal/client"
    "OrdersAgent/mail/internal/config"
    "OrdersAgent/mail/internal/orders"
    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/mail/internal/storage"

    "OrdersAgent/storage/api"
    "OrdersAgent/storage/configdb"
    minio "worker/minio/minio"
)

func main() {
    // грузим .env для DB и MinIO
    _ = godotenv.Load("storage/.env")

    userID := flag.Int("user-id", 0, "ID пользователя для обработки почты")
    flag.Parse()
    if *userID <= 0 {
        log.Fatal("user-id is required, example: --user-id=2")
    }

    // стартовый лог один раз
    log.Printf("mail agent started | user_id=%d", *userID)

    // конфиг IMAP для ящика
    cfg, err := config.Load("mail/internal/config/config.json")
    if err != nil {
        log.Fatalf("config: %v", err)
    }

    // IMAP клиент
    imapClient, err := client.New(cfg)
    if err != nil {
        log.Fatalf("IMAP client: %v", err)
    }
    defer imapClient.Close()

    // конфиг и подключение к Postgres
    dbCfg := configdb.FromEnv()
    db, err := api.ConnectPostgres(dbCfg)
    if err != nil {
        log.Fatalf("db connect: %v", err)
    }
    defer db.Conn.Close()

    // инициализация MinIO
    endpoint := os.Getenv("MINIO_ENDPOINT")
    accessKey := os.Getenv("MINIO_ACCESS_KEY")
    secretKey := os.Getenv("MINIO_SECRET_KEY")
    bucket := os.Getenv("MINIO_BUCKET")
    useSSL := false

    store, err := minio.NewCloudStorage(endpoint, accessKey, secretKey, bucket, useSSL)
    if err != nil {
        log.Fatalf("init cloud storage: %v", err)
    }

    repo := storage.NewDBRepo(db, store)
    processor := orders.New(repo, int64(*userID))

    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    c := make(chan os.Signal, 1)
    signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)

    for {
        select {
        case <-ticker.C:
            ProcessEmails(imapClient, c, processor)
        case <-c:
            log.Printf("mail agent stopped by signal")
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
        return
    }

    log.Printf("found %d unread emails", len(uids))

    for _, uid := range uids {
        select {
        case <-sigChan:
            log.Printf("interrupt while processing, stopping")
            return
        default:
        }

        fetchCmd, err := imap.FetchMessage(uid)
        if err != nil {
            log.Printf("fetch message uid=%d: %v", uid, err)
            continue
        }

        email, err := parser.ParseMessage(uid, fetchCmd)
        if err != nil {
            log.Printf("parse uid=%d: %v", uid, err)
            fetchCmd.Close()
            continue
        }

        if err := processor.ProcessEmail(email); err != nil {
            log.Printf("process uid=%d: %v", uid, err)
        }

        fetchCmd.Close()
        imap.MarkRead(uid)
    }
}