package workflows

import (
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"OrdersAgent/temporal/internal/activities"
)

type ProcessEmailInput struct {
	EmailUID     int64
	TargetUserID int64
}

// ProcessEmailWorkflow — workflow обработки одного письма (по email_uid)
func ProcessEmailWorkflow(ctx workflow.Context, input ProcessEmailInput) error {
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 5 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			MaximumInterval:    10 * time.Second,
			MaximumAttempts:    3,
			BackoffCoefficient: 2.0,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	// 1. Проставить status=processing всем строкам этого письма
	if err := workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "processing").Get(ctx, nil); err != nil {
		return err
	}

	// 2. Прочитать агрегированные данные письма
	var email activities.EmailGroupDTO
	if err := workflow.ExecuteActivity(ctx, "GetEmailGroupActivity", input.EmailUID).Get(ctx, &email); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	// 3. Вызвать LLM (Python) для классификации письма
	var llmRes activities.LLMResultDTO
	if err := workflow.ExecuteActivity(ctx, "RunLLMActivity", &email).Get(ctx, &llmRes); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	// 4. Сохранить результат классификации в process_queue
	if err := workflow.ExecuteActivity(ctx, "SaveClassificationActivity", input.EmailUID, &llmRes).Get(ctx, nil); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	// 5. Завершить статусом done
	if err := workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "done").Get(ctx, nil); err != nil {
		return err
	}

	return nil
}