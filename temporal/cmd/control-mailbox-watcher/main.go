package main

import (
	"context"
	"flag"
	"log"
	"time"

	temporalclient "OrdersAgent/temporal/client"
)

func main() {
	userID := flag.Int64("user-id", 0, "ID пользователя (менеджера), для которого управляем mailbox watcher")
	action := flag.String("action", "", "Действие: pause | resume | stop")
	timeout := flag.Int("timeout", 10, "Таймаут отправки сигнала в секундах")
	flag.Parse()

	if *userID <= 0 {
		log.Fatal("user-id is required, example: --user-id=2")
	}
	if *action == "" {
		log.Fatal("action is required, example: --action=pause")
	}
	if *timeout <= 0 {
		log.Fatal("timeout must be > 0, example: --timeout=10")
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(*timeout)*time.Second)
	defer cancel()

	var err error

	switch *action {
	case "pause":
		err = temporalclient.PauseMailboxWatcher(ctx, *userID)
	case "resume":
		err = temporalclient.ResumeMailboxWatcher(ctx, *userID)
	case "stop":
		err = temporalclient.StopMailboxWatcher(ctx, *userID)
	default:
		log.Fatalf("unsupported action: %s (allowed: pause | resume | stop)", *action)
	}

	if err != nil {
		log.Fatalf("mailbox watcher control failed: %v", err)
	}

	log.Printf("mailbox watcher signal sent successfully | user_id=%d | action=%s", *userID, *action)
}