package main

import (
    "fmt"
    "log"
    "os"
    "os/signal"
    "syscall"
    "time"
    "flag"
    
    "OrdersAgent/mail/internal/client"
    "OrdersAgent/mail/internal/config"
    "OrdersAgent/mail/internal/parser"
    "OrdersAgent/mail/internal/orders"
    "OrdersAgent/mail/internal/storage"
    "github.com/joho/godotenv"

    "OrdersAgent/storage/api"
    "OrdersAgent/storage/configdb"
)

func main() {
    _ = godotenv.Load("storage/.env")

    userID := flag.Int("user-id", 0, "ID пользователя для обработки почты")
	flag.Parse()

	if *userID <= 0 {
		log.Fatal("user-id is required, example: --user-id=2")
	}

	log.Printf("starting mail agent for user_id=%d", *userID)

    // Загружаем конфиг IMAP для КОНКРЕТНОГО ящика
    cfg, err := config.Load("mail/internal/config/config.json")
    if err != nil {
        log.Fatalf("config: %v", err)
    }
    
    fmt.Printf("OrdersAgent v1.0\n")
    fmt.Printf("%s:%d | %s\n", cfg.Host, cfg.Port, cfg.Username)
    
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

    repo := storage.NewDBRepo(db)
    processor := orders.New(repo, int64(*userID))

    ticker := time.NewTicker(10 * time.Second)
    defer ticker.Stop()
    
    c := make(chan os.Signal, 1)
    signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)
    
    for {
        select {
        case <-ticker.C:
            fmt.Println("\nПроверка почты...")
            ProcessEmails(imapClient, c, processor)
        case <-c:
            fmt.Printf("\nОстановка...")
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
        fmt.Println("No new emails")
        return
    }
    
    for _, uid := range uids {
        select {
        case <-sigChan:
            fmt.Println("Прерывание...")
            return
        default:
        }

        fmt.Printf("Processing UID: %d\n", uid)
        
        fetchCmd, err := imap.FetchMessage(uid)
        if err != nil {
            log.Printf("fetch message: %v", err)
            continue
        }
        
        email, err := parser.ParseMessage(uid, fetchCmd)
        if err != nil {
            log.Printf("parse: %v", err)
            fetchCmd.Close()
            continue
        }
        
        if err := processor.ProcessEmail(email); err != nil {
            log.Printf("process email: %v", err)
        }
        
        fetchCmd.Close()
        imap.MarkRead(uid)
    }
}
