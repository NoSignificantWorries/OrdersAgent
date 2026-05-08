package client

import (
	"context"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/contracts"
	"OrdersAgent/temporal/workflows"
)

func SendProcessEmailReviewDecision(ctx context.Context, userID, emailUID int64, modelDecision string) error {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return err
	}
	defer c.Close()

	return c.SignalWorkflow(
		ctx,
		contracts.EmailWorkflowID(userID, emailUID),
		"",
		workflows.ProcessEmailReviewDecisionSignal,
		workflows.ProcessEmailReviewDecisionSignalPayload{
			ModelDecision: modelDecision,
		},
	)
}