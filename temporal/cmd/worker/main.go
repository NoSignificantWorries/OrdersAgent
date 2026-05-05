package main

import (
	"log"

	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"

	"OrdersAgent/temporal/internal/activities"
	"OrdersAgent/temporal/workflows"
)

const TaskQueue = "manager-1-orchestrator"

func main() {
	c, err := client.Dial(client.Options{
		HostPort: "localhost:7233",
	})
	if err != nil {
		log.Fatalf("unable to create Temporal client: %v", err)
	}
	defer c.Close()

	w := worker.New(c, TaskQueue, worker.Options{})

	acts, err := activities.NewQueueActivities()
	if err != nil {
		log.Fatalf("unable to init activities: %v", err)
	}

	// Workflow'и
	w.RegisterWorkflow(workflows.ProcessQueueItemWorkflow) // старый
	w.RegisterWorkflow(workflows.ProcessEmailWorkflow)     // новый

	// Item-level activities
	w.RegisterActivityWithOptions(acts.GetQueueItemActivity, activity.RegisterOptions{
		Name: "GetQueueItemActivity",
	})
	w.RegisterActivityWithOptions(acts.SetStatusActivity, activity.RegisterOptions{
		Name: "SetStatusActivity",
	})

	// Email-level activities
	w.RegisterActivityWithOptions(acts.SetEmailStatusActivity, activity.RegisterOptions{
		Name: "SetEmailStatusActivity",
	})
	w.RegisterActivityWithOptions(acts.GetEmailGroupActivity, activity.RegisterOptions{
		Name: "GetEmailGroupActivity",
	})
	w.RegisterActivityWithOptions(acts.RunLLMActivity, activity.RegisterOptions{
		Name: "RunLLMActivity",
	})
	w.RegisterActivityWithOptions(acts.SaveClassificationActivity, activity.RegisterOptions{
		Name: "SaveClassificationActivity",
	})

	log.Printf("Temporal worker started, task queue = %s", TaskQueue)

	if err := w.Run(worker.InterruptCh()); err != nil {
		log.Fatalf("unable to start worker: %v", err)
	}
}