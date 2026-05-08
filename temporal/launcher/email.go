package client

import (
	"context"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/contracts"
)

const (
	ProcessEmailWorkflowName = contracts.ProcessEmailWorkflowName
	EmailProcessingTaskQueue = contracts.EmailProcessingTaskQueue
)

func EmailWorkflowID(userID, emailUID int64) string {
	return contracts.EmailWorkflowID(userID, emailUID)
}

func StartProcessEmailWorkflow(ctx context.Context, emailUID, userID int64) (string, string, error) {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return "", "", err
	}
	defer c.Close()

	input := contracts.ProcessEmailInput{
		EmailUID:     emailUID,
		TargetUserID: userID,
	}

	we, err := c.ExecuteWorkflow(ctx, sdkclient.StartWorkflowOptions{
		ID:        contracts.EmailWorkflowID(userID, emailUID),
		TaskQueue: contracts.EmailProcessingTaskQueue,
	}, contracts.ProcessEmailWorkflowName, input)
	if err != nil {
		return "", "", err
	}

	return we.GetID(), we.GetRunID(), nil
}