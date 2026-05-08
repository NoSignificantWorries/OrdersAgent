package main

import (
	"context"
	"flag"
	"log"
	"time"

	temporalclient "OrdersAgent/temporal/client"
)

func main() {
	userID := flag.Int64("user-id", 0, "ID пользователя (менеджера), для которого стартуем mailbox watcher")
	interval := flag.Int("interval", 60, "Интервал polling в секундах")
	timeout := flag.Int("timeout", 10, "Таймаут запуска workflow в секундах")
	flag.Parse()

	if *userID <= 0 {
		log.Fatal("user-id is required, example: --user-id=2")
	}
	if *interval <= 0 {
		log.Fatal("interval must be > 0, example: --interval=60")
	}
	if *timeout <= 0 {
		log.Fatal("timeout must be > 0, example: --timeout=10")
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(*timeout)*time.Second)
	defer cancel()

	workflowID, runID, err := temporalclient.StartMailboxWatcherWorkflow(ctx, *userID, *interval)
	if err != nil {
		log.Fatalf("start mailbox watcher workflow: %v", err)
	}

	log.Printf(
		"mailbox watcher started successfully | user_id=%d | workflow_id=%s | run_id=%s | interval_sec=%d",
		*userID,
		workflowID,
		runID,
		*interval,
	)
}