package workflows

import (
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"OrdersAgent/temporal/internal/activities"
)

// Входные данные для обработки одной записи очереди
type ProcessQueueItemInput struct {
    QueueItemID  int64
    TargetUserID int64
}

// ProcessQueueItemWorkflow — workflow обработки одного элемента process_queue
func ProcessQueueItemWorkflow(ctx workflow.Context, input ProcessQueueItemInput) error {
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			MaximumInterval:    10 * time.Second,
			MaximumAttempts:    3,
			BackoffCoefficient: 2.0,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	// 1. Обновить статус на processing
	if err := workflow.ExecuteActivity(ctx, "SetStatusActivity", input.QueueItemID, "processing").Get(ctx, nil); err != nil {
		return err
	}

	// 2. Прочитать запись очереди
	var item activities.QueueItemDTO
	if err := workflow.ExecuteActivity(ctx, "GetQueueItemActivity", input.QueueItemID).Get(ctx, &item); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetStatusActivity", input.QueueItemID, "failed").Get(ctx, nil)
		return err
	}

	// Здесь позже появятся:
	// - DownloadAttachmentActivity
	// - вызов table_worker / llm_worker
	// - сохранение результата

	// 3. Пока просто ставим done
	if err := workflow.ExecuteActivity(ctx, "SetStatusActivity", input.QueueItemID, "done").Get(ctx, nil); err != nil {
		return err
	}

	return nil
}