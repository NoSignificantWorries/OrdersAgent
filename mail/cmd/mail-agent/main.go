package main

import (
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
	"context"
    "encoding/json"
    "net/http"
    "strconv"
    "strings"

    mailsmtp "mail/internal/smtp"

	"github.com/joho/godotenv"

	"mail/internal/config"
	"mail/internal/storage"

	"mail/storage/api"
	"mail/storage/configdb"
	minio "worker/minio/minio"
)

func main() {
	_ = godotenv.Load(".env")

	cfg, err := config.Load("internal/config/config.json")
	if err != nil {
		log.Fatalf("config: %v", err)
	}

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

	smtpClient := mailsmtp.NewClient(mailsmtp.Config{
		Host: "smtp.yandex.ru",
		Port: 465,
	})

	replyMux := http.NewServeMux()

	replyMux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	replyMux.HandleFunc("/emails/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		path := strings.TrimPrefix(r.URL.Path, "/emails/")
		parts := strings.Split(path, "/")
		if len(parts) != 2 || parts[1] != "reply" {
			http.NotFound(w, r)
			return
		}

		emailID, err := strconv.ParseInt(parts[0], 10, 64)
		if err != nil || emailID <= 0 {
			http.Error(w, "invalid email id", http.StatusBadRequest)
			return
		}

		type replyRequest struct {
			Body string `json:"body"`
		}

		var req replyRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid json body", http.StatusBadRequest)
			return
		}

		if strings.TrimSpace(req.Body) == "" {
			http.Error(w, "body is empty", http.StatusBadRequest)
			return
		}

		if err := storage.ReplyToEmail(db, smtpClient, storage.ReplyToEmailRequest{
			EmailID: emailID,
			Body:    req.Body,
		}); err != nil {
			log.Printf("reply send failed | email_id=%d err=%v", emailID, err)
			http.Error(w, "failed to send reply", http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusNoContent)
	})

	replyServer := &http.Server{
		Addr:    ":8080",
		Handler: replyMux,
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	stopChan := make(chan struct{})

	activeWorkers := make(map[int64]bool)
	var mu sync.Mutex
	var wg sync.WaitGroup
	shuttingDown := false

	startNewWorkers := func() {
		users, err := storage.GetUsersWithMailAuth(db)
		if err != nil {
			log.Printf("get users with mail auth: %v", err)
			return
		}

		log.Printf("mail users discovered: %d", len(users))

		for _, u := range users {
			mu.Lock()
			alreadyRunning := activeWorkers[u.ID]
			if shuttingDown {
				mu.Unlock()
				return
			}
			if alreadyRunning {
				mu.Unlock()
				continue
			}
			activeWorkers[u.ID] = true
			mu.Unlock()

			log.Printf("starting user worker | user_id=%d email=%s", u.ID, u.Email)

			wg.Add(1)
			go func(userID int64) {
				defer wg.Done()

				onExit := func(id int64) {
					mu.Lock()
					defer mu.Unlock()
					// При штатном shutdown не трогаем activeWorkers — всё равно выходим
					if shuttingDown {
						return
					}
					log.Printf("user worker exited | user_id=%d", id)
					delete(activeWorkers, id)
				}

				runUserWorker(userID, db, cfg, repo, stopChan, onExit)
			}(u.ID)
		}
	}

	log.Printf("mail agent supervisor started")
	go func() {
		log.Printf("reply http server started on %s", replyServer.Addr)
		if err := replyServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("reply http server: %v", err)
		}
	}()


	startNewWorkers()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			startNewWorkers()
		case sig := <-sigChan:
			log.Printf("shutdown signal received: %v", sig)
			mu.Lock()
			shuttingDown = true
			mu.Unlock()

			close(stopChan)
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			if err := replyServer.Shutdown(shutdownCtx); err != nil {
				log.Printf("reply server shutdown: %v", err)
			}
			cancel()

			wg.Wait()
			log.Printf("all user workers stopped")
			return
		}
	}
}
