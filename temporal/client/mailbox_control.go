package client

import (
	"context"

	sdkclient "go.temporal.io/sdk/client"

	"OrdersAgent/temporal/workflows"
)

func PauseMailboxWatcher(ctx context.Context, userID int64) error {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return err
	}
	defer c.Close()

	return c.SignalWorkflow(ctx,
		workflows.MailboxWatcherWorkflowID(userID),
		"",
		workflows.MailboxWatcherPauseSignal,
		nil,
	)
}

func ResumeMailboxWatcher(ctx context.Context, userID int64) error {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return err
	}
	defer c.Close()

	return c.SignalWorkflow(ctx,
		workflows.MailboxWatcherWorkflowID(userID),
		"",
		workflows.MailboxWatcherResumeSignal,
		nil,
	)
}

func StopMailboxWatcher(ctx context.Context, userID int64) error {
	c, err := sdkclient.Dial(sdkclient.Options{})
	if err != nil {
		return err
	}
	defer c.Close()

	return c.SignalWorkflow(ctx,
		workflows.MailboxWatcherWorkflowID(userID),
		"",
		workflows.MailboxWatcherStopSignal,
		nil,
	)
}