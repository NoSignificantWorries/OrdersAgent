package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/joho/godotenv"

	"mail/storage/api"
	"mail/storage/configdb"
)

func main() {
	_ = godotenv.Load("storage/.env")

	dbCfg := configdb.FromEnv()
	db, err := api.ConnectPostgres(dbCfg)
	if err != nil {
		log.Fatalf("db connect: %v", err)
	}
	defer db.Conn.Close()

	mux := http.NewServeMux()

	mux.HandleFunc("/queue", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		switch r.Method {
		case http.MethodGet:
			statusParam := strings.TrimSpace(r.URL.Query().Get("status"))
			limitStr := r.URL.Query().Get("limit")

			limit := 50
			if limitStr != "" {
				if v, err := strconv.Atoi(limitStr); err == nil && v > 0 && v <= 500 {
					limit = v
				}
			}

			var (
				items []api.QueueEmailItem
				err   error
			)

			if statusParam == "" {
				items, err = db.ListQueueEmails(ctx, limit)
			} else {
				rawStatuses := strings.Split(statusParam, ",")
				statuses := make([]string, 0, len(rawStatuses))
				for _, s := range rawStatuses {
					s = strings.TrimSpace(s)
					if s != "" {
						statuses = append(statuses, s)
					}
				}

				if len(statuses) == 0 {
					items, err = db.ListQueueEmails(ctx, limit)
				} else {
					items, err = db.ListQueueEmailsByStatuses(ctx, statuses, limit)
				}
			}

			if err != nil {
				log.Println("queue get:", err)
				http.Error(w, "internal error", http.StatusInternalServerError)
				return
			}

			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			if err := json.NewEncoder(w).Encode(items); err != nil {
				log.Println("encode:", err)
			}

		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	})

	addr := ":8080"
	if v := os.Getenv("API_ADDR"); v != "" {
		addr = v
	}

	log.Println("storage API listening on", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
