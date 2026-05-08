package main

import (
	"context"
	"flag"
	"log"

	launcher "OrdersAgent/temporal/client"
)

func main() {
	emailUID := flag.Int64("email-uid", 0, "email_uid to process")
	targetUserID := flag.Int64("target-user-id", 0, "target user id")
	flag.Parse()

	if *emailUID == 0 || *targetUserID == 0 {
		log.Fatal("both --email-uid and --target-user-id are required")
	}

	workflowID, runID, err := launcher.StartProcessEmailWorkflow(context.Background(), *emailUID, *targetUserID)
	if err != nil {
		log.Fatalf("start email workflow: %v", err)
	}

	log.Printf("Started email workflow, WorkflowID=%s, RunID=%s", workflowID, runID)
}