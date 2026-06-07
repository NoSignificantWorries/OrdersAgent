package main

import (
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
	"context"
    "io"
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
	
	imapCfg := &config.Config{
		Host: cfg.Host,
		Port: cfg.Port,
	}

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

		contentType := r.Header.Get("Content-Type")

		if strings.HasPrefix(contentType, "multipart/form-data") {
			if err := r.ParseMultipartForm(25 << 20); err != nil {
				http.Error(w, "invalid multipart form", http.StatusBadRequest)
				return
			}
		} else {
			if err := r.ParseForm(); err != nil {
				http.Error(w, "invalid form", http.StatusBadRequest)
				return
			}
		}

		log.Printf("reply parsed | email_id=%d content_type=%q body=%q", emailID, contentType, r.FormValue("body"))

		body := strings.TrimSpace(r.FormValue("body"))
		if body == "" {
			http.Error(w, "body is empty", http.StatusBadRequest)
			return
		}

		const maxAttachmentsCount = 5
		const maxAttachmentSize = 10 << 20 // 10 MB

		var attachments []storage.ReplyAttachment

		if r.MultipartForm != nil {
			files := r.MultipartForm.File["attachments"]

			if len(files) > maxAttachmentsCount {
				http.Error(w, "too many attachments", http.StatusBadRequest)
				return
			}

			attachments = make([]storage.ReplyAttachment, 0, len(files))

			for _, fh := range files {
				src, err := fh.Open()
				if err != nil {
					http.Error(w, "failed to open attachment", http.StatusBadRequest)
					return
				}

				data, err := io.ReadAll(src)
				_ = src.Close()
				if err != nil {
					http.Error(w, "failed to read attachment", http.StatusBadRequest)
					return
				}

				if len(data) > maxAttachmentSize {
					http.Error(w, "attachment too large", http.StatusBadRequest)
					return
				}

				partContentType := strings.TrimSpace(fh.Header.Get("Content-Type"))
				if partContentType == "" {
					partContentType = "application/octet-stream"
				}

				attachments = append(attachments, storage.ReplyAttachment{
					Filename:    fh.Filename,
					ContentType: partContentType,
					Data:        data,
				})
			}
		}

		log.Printf("reply send start | email_id=%d attachments=%d", emailID, len(attachments))

		if err := storage.ReplyToEmail(db, smtpClient, imapCfg, storage.ReplyToEmailRequest{
			EmailID:     emailID,
			Body:        body,
			Attachments: attachments,
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
