// Worker, отвечающий за PollMailboxActivity и MailboxWatcherWorkflow для конкретного менеджера.
package main

import (
	"log"
	"os"
	"strconv"

	sdkclient "go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"

	"OrdersAgent/temporal/client"
	"OrdersAgent/temporal/internal/activities"
	"OrdersAgent/temporal/workflows"
)

func main() {
	managerIDStr := os.Getenv("MANAGER_ID")
	if managerIDStr == "" {
		log.Fatal("MANAGER_ID env is required")
	}
	managerID, err := strconv.ParseInt(managerIDStr, 10, 64)
	if err != nil || managerID <= 0 {
		log.Fatalf("invalid MANAGER_ID: %v", managerIDStr)
	}

	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		log.Fatalf("unable to create Temporal client: %v", err)
	}
	defer c.Close()

	queue := client.MailboxSyncTaskQueue(managerID)

	w := worker.New(c, queue, worker.Options{})

	w.RegisterWorkflow(workflows.MailboxWatcherWorkflow)
	w.RegisterActivity(activities.PollMailboxActivity)

	log.Printf("mailbox worker started | manager_id=%d | queue=%s", managerID, queue)

	if err := w.Run(worker.InterruptCh()); err != nil {
		log.Fatalf("unable to start mailbox worker: %v", err)
	}
}