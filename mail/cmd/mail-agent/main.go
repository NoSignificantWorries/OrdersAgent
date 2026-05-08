// DEPRECATED: mail-agent заменён Temporal MailboxWatcherWorkflow + PollMailboxActivity.
// В dev/production запускать watcher, а не mail-agent.
//go:build legacy_mail_agent
package main

import (
    "context"
    "flag"
    "log"
    "os"

    "github.com/joho/godotenv"

    "OrdersAgent/mail/client"
    "OrdersAgent/mail/config"
    "OrdersAgent/mail/orders"
    "OrdersAgent/mail/storage"
    "OrdersAgent/mail/sync"

    "OrdersAgent/storage/api"
    "OrdersAgent/storage/configdb"
    minio "worker/minio/minio"
)

func main() {
    _ = godotenv.Load("storage/.env")

    userID := flag.Int("user-id", 0, "ID пользователя для обработки почты")
    flag.Parse()
    if *userID <= 0 {
        log.Fatal("user-id is required, example: --user-id=2")
    }

    log.Printf("mail agent started | user_id=%d", *userID)

    cfg, err := config.Load("mail/internal/config/config.json")
    if err != nil {
        log.Fatalf("config: %v", err)
    }

    imapClient, err := client.New(cfg)
    if err != nil {
        log.Fatalf("IMAP client: %v", err)
    }
    defer imapClient.Close()

    dbCfg := configdb.FromEnv()
    db, err := api.ConnectPostgres(dbCfg)
    if err != nil {
        log.Fatalf("db connect: %v", err)
    }
    defer db.Conn.Close()

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
    processor := orders.New(repo, int64(*userID), nil)

    syncService := sync.New(processor)

    // Один проход
    if err := syncService.SyncMailboxOnce(context.Background(), imapClient); err != nil {
        log.Printf("sync mailbox once: %v", err)
    }

    log.Printf("mail agent finished one sync | user_id=%d", *userID)
}