package client

import (
	"context"
	"fmt"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/workflows"
)

const TaskQueue = "manager-1-orchestrator"

// StartProcessEmailWorkflow запускает workflow для одного письма (email_uid, targetUserID).
func StartProcessEmailWorkflow(ctx context.Context, emailUID, targetUserID int64) (string, string, error) {
	c, err := sdkclient.Dial(sdkclient.Options{
		HostPort: "localhost:7233",
	})
	if err != nil {
		return "", "", fmt.Errorf("dial temporal: %w", err)
	}
	defer c.Close()

	workflowID := fmt.Sprintf("manager-%d-email-%d", targetUserID, emailUID)

	opts := sdkclient.StartWorkflowOptions{
		ID:        workflowID,
		TaskQueue: TaskQueue,
	}

	input := workflows.ProcessEmailInput{
		EmailUID:     emailUID,
		TargetUserID: targetUserID,
	}

	we, err := c.ExecuteWorkflow(ctx, opts, workflows.ProcessEmailWorkflow, input)
	if err != nil {
		return "", "", fmt.Errorf("start email workflow: %w", err)
	}

	return we.GetID(), we.GetRunID(), nil
}