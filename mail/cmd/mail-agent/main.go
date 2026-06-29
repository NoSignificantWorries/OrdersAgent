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
	"fmt"
	"encoding/json"

    mailsmtp "mail/internal/smtp"

	"github.com/joho/godotenv"

	"mail/internal/config"
	"mail/internal/storage"

	"mail/storage/api"
	"mail/storage/configdb"
	minio "worker/minio/minio"
)

func writeJSONError(w http.ResponseWriter, status int, detail string) {
    w.Header().Set("Content-Type", "application/json; charset=utf-8")
    w.WriteHeader(status)
    _ = json.NewEncoder(w).Encode(map[string]string{
        "detail": detail,
    })
}

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
	incomingBucket := os.Getenv("MINIO_BUCKET")
	outgoingBucket := os.Getenv("MINIO_OUTGOING_BUCKET")
	useSSL := false

	incomingStore, err := minio.NewCloudStorage(endpoint, accessKey, secretKey, incomingBucket, useSSL)
	if err != nil {
		log.Fatalf("init incoming cloud storage: %v", err)
	}

	outgoingStore, err := minio.NewCloudStorage(endpoint, accessKey, secretKey, outgoingBucket, useSSL)
	if err != nil {
		log.Fatalf("init outgoing cloud storage: %v", err)
	}

	repo := storage.NewDBRepo(db, incomingStore, outgoingStore)
	dbRepo, ok := repo.(*storage.DBRepo)
	if !ok {
		log.Fatalf("repo type assertion to *storage.DBRepo failed")
	}

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
		// if r.Method != http.MethodPost {
		// 	http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		// 	return
		// }

		path := strings.Trim(strings.TrimPrefix(r.URL.Path, "/emails/"), "/")
        parts := strings.Split(path, "/")

        const maxRequestBodySize = 30 << 20 // 30 MB
        r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodySize)

        contentType := r.Header.Get("Content-Type")

		if len(parts) == 2 && parts[1] == "forward-draft" {
            if r.Method != http.MethodGet && r.Method != http.MethodPost {
                http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
                return
            }

            emailID, err := strconv.ParseInt(parts[0], 10, 64)
            if err != nil || emailID <= 0 {
                writeJSONError(w, http.StatusBadRequest, "invalid email id")
                return
            }

            draft, err := storage.BuildForwardDraft(db, emailID)
            if err != nil {
                log.Printf("forward draft failed | email_id=%d err=%v", emailID, err)
                writeJSONError(w, http.StatusInternalServerError, "failed to build forward draft")
                return
            }

            w.Header().Set("Content-Type", "application/json; charset=utf-8")
            if err := json.NewEncoder(w).Encode(draft); err != nil {
                log.Printf("forward draft encode failed | email_id=%d err=%v", emailID, err)
            }
            return
        }

		if r.Method != http.MethodPost {
            http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
            return
        }

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

		const maxAttachmentsCount = 10
		const maxAttachmentSize = 10 << 20 // 10 MB
		const maxTotalAttachmentsSize = 25 << 20 // 25 MB

		const (
			ErrTooManyFiles        = "много файлов, лимит 10 штук"
			ErrFileTooLarge        = "вес превышен: файл весит больше 10МБ"
			ErrTotalSizeExceeded   = "вес превышен: общий вес письма выше 25МБ"
		)

		readAttachments := func() ([]storage.SendAttachment, error) {
			var attachments []storage.SendAttachment
			totalSize := 0

			if r.MultipartForm == nil {
				return attachments, nil
			}

			files := r.MultipartForm.File["attachments"]
			if len(files) > maxAttachmentsCount {
				return nil, fmt.Errorf(ErrTooManyFiles)
			}

			attachments = make([]storage.SendAttachment, 0, len(files))

			for _, fh := range files {
				src, err := fh.Open()
				if err != nil {
					return nil, fmt.Errorf("failed to open attachment")
				}

				data, err := io.ReadAll(src)
				_ = src.Close()
				if err != nil {
					return nil, fmt.Errorf("failed to read attachment")
				}

				if len(data) > maxAttachmentSize {
					return nil, fmt.Errorf(ErrFileTooLarge)
				}

				totalSize += len(data)
				if totalSize > maxTotalAttachmentsSize {
					return nil, fmt.Errorf(ErrTotalSizeExceeded)
				}

				partContentType := strings.TrimSpace(fh.Header.Get("Content-Type"))
				if partContentType == "" {
					partContentType = "application/octet-stream"
				}

				attachments = append(attachments, storage.SendAttachment{
					Filename:    fh.Filename,
					ContentType: partContentType,
					Data:        data,
				})
			}

			return attachments, nil
		}

		readIncludeDocumentIDs := func() ([]int64, error) {
			rawValues := r.Form["include_document_ids"]
			if len(rawValues) == 0 {
				return []int64{}, nil
			}

			ids := make([]int64, 0, len(rawValues))
			seen := make(map[int64]struct{})

			for _, raw := range rawValues {
				raw = strings.TrimSpace(raw)
				if raw == "" {
					continue
				}

				id, err := strconv.ParseInt(raw, 10, 64)
				if err != nil || id <= 0 {
					return nil, fmt.Errorf("invalid include_document_ids")
				}

				if _, ok := seen[id]; ok {
					continue
				}
				seen[id] = struct{}{}
				ids = append(ids, id)
			}

			return ids, nil
		}

		if len(parts) == 1 && parts[0] == "send" {
			mailbox := strings.TrimSpace(r.FormValue("mailbox"))
			to := strings.TrimSpace(r.FormValue("to"))
			subject := strings.TrimSpace(r.FormValue("subject"))
			body := strings.TrimSpace(r.FormValue("body"))

			if mailbox == "" {
				http.Error(w, "mailbox is empty", http.StatusBadRequest)
				return
			}
			if to == "" {
				http.Error(w, "to is empty", http.StatusBadRequest)
				return
			}
			if body == "" {
				http.Error(w, "body is empty", http.StatusBadRequest)
				return
			}

			attachments, err := readAttachments()
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			log.Printf("send start | mailbox=%s to=%q subject=%q attachments=%d", mailbox, to, subject, len(attachments))

			if err := storage.SendEmail(db, dbRepo, smtpClient, imapCfg, storage.SendEmailRequest{
				Mailbox:     mailbox,
				To:          to,
				Subject:     subject,
				Body:        body,
				Attachments: attachments,
			}); err != nil {
				log.Printf("send failed | mailbox=%s err=%v", mailbox, err)
				http.Error(w, "failed to send email", http.StatusInternalServerError)
				return
			}

			w.WriteHeader(http.StatusNoContent)
			return
		}

		if len(parts) == 2 && parts[1] == "reply" {
			emailID, err := strconv.ParseInt(parts[0], 10, 64)
			if err != nil || emailID <= 0 {
				http.Error(w, "invalid email id", http.StatusBadRequest)
				return
			}

			log.Printf("reply parsed | email_id=%d content_type=%q body=%q", emailID, contentType, r.FormValue("body"))

			body := strings.TrimSpace(r.FormValue("body"))
			if body == "" {
				http.Error(w, "body is empty", http.StatusBadRequest)
				return
			}

			rawAttachments, err := readAttachments()
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			attachments := make([]storage.ReplyAttachment, 0, len(rawAttachments))
			for _, att := range rawAttachments {
				attachments = append(attachments, storage.ReplyAttachment{
					Filename:    att.Filename,
					ContentType: att.ContentType,
					Data:        att.Data,
				})
			}

			log.Printf("reply send start | email_id=%d attachments=%d", emailID, len(attachments))

			if err := storage.ReplyToEmail(db, dbRepo, smtpClient, imapCfg, storage.ReplyToEmailRequest{
				EmailID:     emailID,
				Body:        body,
				Attachments: attachments,
			}); err != nil {
				log.Printf("reply send failed | email_id=%d err=%v", emailID, err)
				http.Error(w, "failed to send reply", http.StatusInternalServerError)
				return
			}

			w.WriteHeader(http.StatusNoContent)
			return
		}

		if len(parts) == 2 && parts[1] == "forward" {
			emailID, err := strconv.ParseInt(parts[0], 10, 64)
			if err != nil || emailID <= 0 {
				http.Error(w, "invalid email id", http.StatusBadRequest)
				return
			}

			to := strings.TrimSpace(r.FormValue("to"))
			body := strings.TrimSpace(r.FormValue("body"))

			if to == "" {
				http.Error(w, "to is empty", http.StatusBadRequest)
				return
			}
			if body == "" {
				http.Error(w, "body is empty", http.StatusBadRequest)
				return
			}

			includeDocumentIDs, err := readIncludeDocumentIDs()
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			attachments, err := readAttachments()
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			log.Printf(
				"forward send start | email_id=%d to=%q include_docs=%d new_attachments=%d",
				emailID,
				to,
				len(includeDocumentIDs),
				len(attachments),
			)

			if err := storage.ForwardEmail(db, dbRepo, smtpClient, imapCfg, storage.ForwardEmailRequest{
				EmailID:            emailID,
				To:                 to,
				Body:               body,
				IncludeDocumentIDs: includeDocumentIDs,
				Attachments:        attachments,
			}); err != nil {
				log.Printf("forward send failed | email_id=%d err=%v", emailID, err)
				http.Error(w, "failed to forward email", http.StatusInternalServerError)
				return
			}

			w.WriteHeader(http.StatusNoContent)
			return
		}

		http.NotFound(w, r)
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
