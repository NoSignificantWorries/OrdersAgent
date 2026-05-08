package client

import (
	"context"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/workflows"
)

func StartProcessEmailWorkflow(ctx context.Context, emailUID, userID int64) (string, string, error) {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return "", "", err
	}
	defer c.Close()

	workflowID := workflows.EmailWorkflowID(userID, emailUID) // если/когда вынесем функцию ID

	we, err := c.ExecuteWorkflow(ctx, sdkclient.StartWorkflowOptions{
		ID:        workflowID,
		TaskQueue: EmailProcessingTaskQueue, // единая очередь для обработки писем
	}, workflows.ProcessEmailWorkflow, emailUID, userID)
	if err != nil {
		return "", "", err
	}

	return we.GetID(), we.GetRunID(), nil
}