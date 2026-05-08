package activities

import (
	"context"
	"errors"
	"log"
	"os"

	"github.com/joho/godotenv"

	"OrdersAgent/mail/client"
	"OrdersAgent/mail/config"
	"OrdersAgent/mail/orders"
	"OrdersAgent/mail/storage"
	mailsync "OrdersAgent/mail/sync"
	emaillauncher "OrdersAgent/temporal/launcher"

	"OrdersAgent/storage/api"
	"OrdersAgent/storage/configdb"
	minio "worker/minio/minio"
)

type PollMailboxInput struct {
	UserID int64 `json:"user_id"`
}

type PollMailboxResult struct {
	ProcessedEmails int `json:"processed_emails"`
}

var ErrInvalidUserID = errors.New("invalid user id")

func PollMailboxActivity(ctx context.Context, input PollMailboxInput) (PollMailboxResult, error) {
	_ = godotenv.Load("storage/.env")

	userID := input.UserID
	if userID <= 0 {
		return PollMailboxResult{}, ErrInvalidUserID
	}

	log.Printf("poll mailbox activity started | user_id=%d", userID)

	cfg, err := config.Load("mail/config/config.json")
	if err != nil {
		log.Printf("poll mailbox: config: %v", err)
		return PollMailboxResult{}, err
	}

	imapClient, err := client.New(cfg)
	if err != nil {
		log.Printf("poll mailbox: IMAP client: %v", err)
		return PollMailboxResult{}, err
	}
	defer imapClient.Close()

	dbCfg := configdb.FromEnv()
	db, err := api.ConnectPostgres(dbCfg)
	if err != nil {
		log.Printf("poll mailbox: db connect: %v", err)
		return PollMailboxResult{}, err
	}
	defer db.Conn.Close()

	endpoint := os.Getenv("MINIO_ENDPOINT")
	accessKey := os.Getenv("MINIO_ACCESS_KEY")
	secretKey := os.Getenv("MINIO_SECRET_KEY")
	bucket := os.Getenv("MINIO_BUCKET")
	useSSL := false

	store, err := minio.NewCloudStorage(endpoint, accessKey, secretKey, bucket, useSSL)
	if err != nil {
		log.Printf("poll mailbox: init cloud storage: %v", err)
		return PollMailboxResult{}, err
	}

	repo := storage.NewDBRepo(db, store)

	processor := orders.New(repo, userID, func(cbCtx context.Context, emailUID, userID int64) error {
		_, _, err := emaillauncher.StartProcessEmailWorkflow(cbCtx, emailUID, userID)
		return err
	})

	syncService := mailsync.New(processor)

	if err := syncService.SyncMailboxOnce(ctx, imapClient); err != nil {
		log.Printf("poll mailbox: sync mailbox once: %v", err)
		return PollMailboxResult{}, err
	}

	log.Printf("poll mailbox activity finished | user_id=%d", userID)

	return PollMailboxResult{
		ProcessedEmails: 0,
	}, nil
}