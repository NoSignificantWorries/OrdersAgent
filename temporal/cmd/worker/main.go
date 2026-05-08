package main

import (
	"log"

	"OrdersAgent/temporal/contracts"
	emaillauncher "OrdersAgent/temporal/launcher"
	"OrdersAgent/temporal/internal/activities"
	"OrdersAgent/temporal/workflows"

	"go.temporal.io/sdk/activity"
	sdkclient "go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	workflowapi "go.temporal.io/sdk/workflow"
)

const TaskQueue = contracts.EmailProcessingTaskQueue

func main() {
	c, err := sdkclient.Dial(sdkclient.Options{
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

	w.RegisterWorkflowWithOptions(workflows.ProcessEmailWorkflow, workflowapi.RegisterOptions{
		Name: emaillauncher.ProcessEmailWorkflowName,
	})
	w.RegisterWorkflow(workflows.MailboxWatcherWorkflow)

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
	w.RegisterActivityWithOptions(acts.EnqueueFilesProcessingActivity, activity.RegisterOptions{
		Name: "EnqueueFilesProcessingActivity",
	})
	w.RegisterActivity(activities.PollMailboxActivity)

	log.Printf("Temporal worker started, task queue = %s", TaskQueue)

	if err := w.Run(worker.InterruptCh()); err != nil {
		log.Fatalf("unable to start worker: %v", err)
	}
}