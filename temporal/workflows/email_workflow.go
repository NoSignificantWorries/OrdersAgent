package workflows

import (
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"OrdersAgent/temporal/contracts"
	"OrdersAgent/temporal/internal/activities"
)

const ProcessEmailReviewDecisionSignal = "process-email-review-decision"

type ProcessEmailReviewDecisionSignalPayload struct {
	ModelDecision string `json:"model_decision"`
}

func ProcessEmailWorkflow(ctx workflow.Context, input contracts.ProcessEmailInput) error {
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

	if err := workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "processing").Get(ctx, nil); err != nil {
		return err
	}

	var email activities.EmailGroupDTO
	if err := workflow.ExecuteActivity(ctx, "GetEmailGroupActivity", input.EmailUID).Get(ctx, &email); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	var llmRes activities.LLMResultDTO
	if err := workflow.ExecuteActivity(ctx, "RunLLMActivity", &email).Get(ctx, &llmRes); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	if err := workflow.ExecuteActivity(ctx, "SaveClassificationActivity", input.EmailUID, &llmRes).Get(ctx, nil); err != nil {
		_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
		return err
	}

	finalDecision := llmRes.ModelDecision

	if llmRes.ModelDecision == "review" {
		logger := workflow.GetLogger(ctx)
		logger.Info("ProcessEmailWorkflow waiting for review decision",
			"email_uid", input.EmailUID,
			"target_user_id", input.TargetUserID,
		)

		reviewSignalCh := workflow.GetSignalChannel(ctx, ProcessEmailReviewDecisionSignal)

		var signalPayload ProcessEmailReviewDecisionSignalPayload
		err := reviewSignalCh.Receive(ctx, &signalPayload)
		if err != nil {
			_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
			return err
		}

		logger.Info("ProcessEmailWorkflow received review decision",
			"email_uid", input.EmailUID,
			"target_user_id", input.TargetUserID,
			"model_decision", signalPayload.ModelDecision,
		)

		if signalPayload.ModelDecision != "auto_0" && signalPayload.ModelDecision != "auto_1" {
			_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
			return temporal.NewNonRetryableApplicationError(
				"invalid review decision",
				"InvalidReviewDecision",
				nil,
			)
		}

		finalDecision = signalPayload.ModelDecision
	}

	if finalDecision == "auto_0" { //позже добавить вызов с  || finalDecision == "auto_1"
		if err := workflow.ExecuteActivity(ctx, "EnqueueFilesProcessingActivity", input.EmailUID).Get(ctx, nil); err != nil {
			_ = workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "failed").Get(ctx, nil)
			return err
		}
	}

	if err := workflow.ExecuteActivity(ctx, "SetEmailStatusActivity", input.EmailUID, "done").Get(ctx, nil); err != nil {
		return err
	}

	return nil
}