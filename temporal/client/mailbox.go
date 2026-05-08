package client

import (
	"context"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/workflows"
)

func StartMailboxWatcherWorkflow(ctx context.Context, userID int64, pollIntervalSec int) (string, string, error) {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return "", "", err
	}
	defer c.Close()

	workflowID := workflows.MailboxWatcherWorkflowID(userID)

	we, err := c.ExecuteWorkflow(ctx, sdkclient.StartWorkflowOptions{
		ID:        workflowID,
		TaskQueue: MailboxSyncTaskQueue(userID),
	}, workflows.MailboxWatcherWorkflow, workflows.MailboxWatcherInput{
		UserID:          userID,
		PollIntervalSec: pollIntervalSec,
		Iteration:       0,
	})
	if err != nil {
		return "", "", err
	}

	return we.GetID(), we.GetRunID(), nil
}