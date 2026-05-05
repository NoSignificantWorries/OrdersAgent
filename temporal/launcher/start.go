package launcher

import (
	"context"
	"fmt"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/workflows"
)

const TaskQueue = "manager-1-orchestrator"

func StartProcessQueueWorkflow(ctx context.Context, queueID int64, targetUserID int64) (string, string, error) {
	c, err := sdkclient.Dial(sdkclient.Options{
		HostPort: "localhost:7233",
	})
	if err != nil {
		return "", "", fmt.Errorf("dial temporal: %w", err)
	}
	defer c.Close()

	workflowID := fmt.Sprintf("manager-%d-item-%d", targetUserID, queueID)

	opts := sdkclient.StartWorkflowOptions{
		ID:        workflowID,
		TaskQueue: TaskQueue,
	}

	input := workflows.ProcessQueueItemInput{
		QueueItemID:  queueID,
		TargetUserID: targetUserID,
	}

	we, err := c.ExecuteWorkflow(ctx, opts, workflows.ProcessQueueItemWorkflow, input)
	if err != nil {
		return "", "", fmt.Errorf("execute workflow %s: %w", workflowID, err)
	}

	return we.GetID(), we.GetRunID(), nil
}