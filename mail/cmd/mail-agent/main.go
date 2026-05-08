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
	_ = godotenv.Load("storage/.env")

	userID := flag.Int("user-id", 0, "ID пользователя для обработки почты")
	flag.Parse()
	if *userID <= 0 {
		log.Fatal("user-id is required, example: --user-id=2")
	}

	log.Printf("mail agent started | user_id=%d", *userID)

	// Общий IMAP-конфиг без логина/пароля приложения
	cfg, err := config.Load("mail/internal/config/config.json")
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	// Подключение к Postgres
	dbCfg := configdb.FromEnv()
	db, err := api.ConnectPostgres(dbCfg)
	if err != nil {
		log.Fatalf("db connect: %v", err)
	}
	defer db.Conn.Close()

	// Достаём почтовые OAuth-данные пользователя из users:
	// email, mail_access_token, mail_refresh_token, mail_access_expires_at
	mailAuth, err := storage.GetUserMailAuth(db, int64(*userID))
	if err != nil {
		log.Fatalf("get user mail auth: %v", err)
	}

	if mailAuth.AccessToken == "" {
		log.Fatal("empty mail access token")
	}

	// Если срок access_token истёк или скоро истечёт, обновляем.
	if time.Now().After(mailAuth.AccessExpiresAt.Add(-1 * time.Minute)) {
		log.Printf("access token expired or about to expire, refreshing | user_id=%d", *userID)

		// TODO: реализовать refresh в отдельной функции, например:
		// newAuth, err := client.RefreshYandexToken(
		//     cfg.OAuthTokenURL,
		//     os.Getenv("YANDEX_CLIENT_ID"),
		//     os.Getenv("YANDEX_CLIENT_SECRET"),
		//     mailAuth.RefreshToken,
		// )
		// if err != nil {
		//     log.Fatalf("refresh token: %v", err)
		// }
		//
		// if err := storage.UpdateUserMailTokens(db, int64(*userID), newAuth); err != nil {
		//     log.Fatalf("update mail tokens: %v", err)
		// }
		//
		// mailAuth = newAuth

		log.Printf("WARNING: token refresh is not implemented yet")
	}

	// IMAP-клиент по OAuth2/XOAUTH2
	imapClient, err := client.NewOAuth(cfg, mailAuth.Email, mailAuth.AccessToken)
	if err != nil {
		log.Fatalf("IMAP client: %v", err)
	}
	defer imapClient.Close()

	// MinIO
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

	// Первый проход сразу после старта
	ProcessEmails(imapClient, c, processor)

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

		if err := imap.MarkRead(uid); err != nil {
			log.Printf("mark read uid=%d: %v", uid, err)
		}
	}
}