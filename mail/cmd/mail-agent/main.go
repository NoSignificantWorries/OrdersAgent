package main

import (
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/joho/godotenv"

	"OrdersAgent/mail/internal/config"
	"OrdersAgent/mail/internal/storage"

	"OrdersAgent/storage/api"
	"OrdersAgent/storage/configdb"
	minio "worker/minio/minio"
)

func main() {
	_ = godotenv.Load("storage/.env")

	cfg, err := config.Load("mail/internal/config/config.json")
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
			wg.Wait()
			log.Printf("all user workers stopped")
			return
		}
	}
}