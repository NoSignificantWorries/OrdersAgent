package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
    "strconv"

    "github.com/joho/godotenv"

    "OrdersAgent/storage/api"
    "OrdersAgent/storage/configdb"
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
			status := r.URL.Query().Get("status") // например wait
			limitStr := r.URL.Query().Get("limit")
			limit := 50
			if limitStr != "" {
				if v, err := strconv.Atoi(limitStr); err == nil && v > 0 && v <= 500 {
					limit = v
				}
			}

			items, err := db.ListQueue(ctx, status, limit)
			if err != nil {
				log.Println("ListQueue:", err)
				http.Error(w, "internal error", http.StatusInternalServerError)
				return
			}

			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			if err := json.NewEncoder(w).Encode(items); err != nil {
				log.Println("encode:", err)
			}

		case http.MethodPost:
			var in struct {
				AssignedTo   *int64  `json:"assigned_to"`
				EmailSubject string  `json:"email_subject"`
				EmailBody    string  `json:"email_body"`
				DocumentName *string `json:"document_name"`
				Status       string  `json:"status"`
			}

			if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
				http.Error(w, "bad json", http.StatusBadRequest)
				return
			}

			if in.EmailSubject == "" {
				http.Error(w, "subject and body are required", http.StatusBadRequest)
				return
			}

			status := in.Status
			if status == "" {
				status = "wait"
			}

			item := api.QueueItem{
				AssignedTo: in.AssignedTo,
				Subject:    in.EmailSubject,
				Body:       in.EmailBody,
				DocName:    in.DocumentName,
				Status:     status,
			}

			if err := db.InsertQueueItem(ctx, item); err != nil {
				log.Println("InsertQueueItem:", err)
				http.Error(w, "internal error", http.StatusInternalServerError)
				return
			}

			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(http.StatusCreated)
			if err := json.NewEncoder(w).Encode(item); err != nil {
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
