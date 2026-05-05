package main

import (
	"context"
	"flag"
	"log"

	"OrdersAgent/temporal/client/launcher"
)

func main() {
	queueID := flag.Int64("queue-id", 0, "process_queue id")
	targetUserID := flag.Int64("target-user-id", 0, "target user id")
	flag.Parse()

	if *queueID == 0 {
		log.Fatal("queue-id is required")
	}
	if *targetUserID == 0 {
		log.Fatal("target-user-id is required")
	}

	workflowID, runID, err := launcher.StartProcessQueueWorkflow(context.Background(), *queueID, *targetUserID)
	if err != nil {
		log.Fatalf("unable to start workflow: %v", err)
	}

	log.Printf("Started workflow, WorkflowID=%s, RunID=%s", workflowID, runID)
}