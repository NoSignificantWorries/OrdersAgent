package workflows

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"OrdersAgent/temporal/internal/activities"
)

const (
	MailboxWatcherPauseSignal  = "mailbox-watcher-pause"
	MailboxWatcherResumeSignal = "mailbox-watcher-resume"
	MailboxWatcherStopSignal   = "mailbox-watcher-stop"
)

type MailboxWatcherInput struct {
	UserID          int64 `json:"user_id"`
	PollIntervalSec int   `json:"poll_interval_sec"`
	Iteration       int   `json:"iteration"`
}

type MailboxWatcherResult struct {
	LastProcessedEmails int  `json:"last_processed_emails"`
	Stopped             bool `json:"stopped"`
}

func MailboxWatcherWorkflowID(userID int64) string {
	return fmt.Sprintf("mailbox-watcher-user-%d", userID)
}

func MailboxWatcherWorkflow(ctx workflow.Context, input MailboxWatcherInput) (MailboxWatcherResult, error) {
	logger := workflow.GetLogger(ctx)

	if input.UserID <= 0 {
		return MailboxWatcherResult{}, temporal.NewNonRetryableApplicationError("invalid user id", "InvalidInput", nil)
	}
	if input.PollIntervalSec <= 0 {
		input.PollIntervalSec = 60
	}

	const maxIterationsBeforeContinueAsNew = 500

	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 5 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    5 * time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    1 * time.Minute,
			MaximumAttempts:    0,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	pauseCh := workflow.GetSignalChannel(ctx, MailboxWatcherPauseSignal)
	resumeCh := workflow.GetSignalChannel(ctx, MailboxWatcherResumeSignal)
	stopCh := workflow.GetSignalChannel(ctx, MailboxWatcherStopSignal)

	var last activities.PollMailboxResult
	paused := false

	drainSignals := func() bool {
		shouldStop := false

		for {
			handled := false

			if stopCh.ReceiveAsync(nil) {
				shouldStop = true
				handled = true
				logger.Info("mailbox watcher received stop signal",
					"user_id", input.UserID,
					"iteration", input.Iteration,
				)
			}

			if pauseCh.ReceiveAsync(nil) {
				if !paused {
					paused = true
					logger.Info("mailbox watcher paused",
						"user_id", input.UserID,
						"iteration", input.Iteration,
					)
				}
				handled = true
			}

			if resumeCh.ReceiveAsync(nil) {
				if paused {
					paused = false
					logger.Info("mailbox watcher resumed",
						"user_id", input.UserID,
						"iteration", input.Iteration,
					)
				}
				handled = true
			}

			if !handled {
				break
			}
		}

		return shouldStop
	}

	for {
		if drainSignals() {
			return MailboxWatcherResult{
				LastProcessedEmails: last.ProcessedEmails,
				Stopped:             true,
			}, nil
		}

		if paused {
			selector := workflow.NewSelector(ctx)

			selector.AddReceive(stopCh, func(c workflow.ReceiveChannel, more bool) {
				c.Receive(ctx, nil)
				logger.Info("mailbox watcher received stop signal while paused",
					"user_id", input.UserID,
					"iteration", input.Iteration,
				)
				paused = false
				last = activities.PollMailboxResult{
					ProcessedEmails: last.ProcessedEmails,
				}
				// stop обработаем после Select через флаг ниже
			})

			resumed := false
			stopped := false

			selector = workflow.NewSelector(ctx)
			selector.AddReceive(stopCh, func(c workflow.ReceiveChannel, more bool) {
				c.Receive(ctx, nil)
				stopped = true
				logger.Info("mailbox watcher received stop signal while paused",
					"user_id", input.UserID,
					"iteration", input.Iteration,
				)
			})
			selector.AddReceive(resumeCh, func(c workflow.ReceiveChannel, more bool) {
				c.Receive(ctx, nil)
				paused = false
				resumed = true
				logger.Info("mailbox watcher resumed",
					"user_id", input.UserID,
					"iteration", input.Iteration,
				)
			})
			selector.AddReceive(pauseCh, func(c workflow.ReceiveChannel, more bool) {
				c.Receive(ctx, nil)
				logger.Info("mailbox watcher received pause signal while already paused",
					"user_id", input.UserID,
					"iteration", input.Iteration,
				)
			})

			selector.Select(ctx)

			if stopped {
				return MailboxWatcherResult{
					LastProcessedEmails: last.ProcessedEmails,
					Stopped:             true,
				}, nil
			}

			if resumed {
				if drainSignals() {
					return MailboxWatcherResult{
						LastProcessedEmails: last.ProcessedEmails,
						Stopped:             true,
					}, nil
				}
			}

			continue
		}

		input.Iteration++

		err := workflow.ExecuteActivity(ctx, activities.PollMailboxActivity, activities.PollMailboxInput{
			UserID: input.UserID,
		}).Get(ctx, &last)
		if err != nil {
			logger.Error("poll mailbox activity failed",
				"user_id", input.UserID,
				"error", err,
				"iteration", input.Iteration,
			)
		} else {
			logger.Info("poll mailbox activity finished",
				"user_id", input.UserID,
				"processed_emails", last.ProcessedEmails,
				"iteration", input.Iteration,
			)
		}

		if input.Iteration >= maxIterationsBeforeContinueAsNew {
			logger.Info("mailbox watcher ContinueAsNew",
				"user_id", input.UserID,
				"iteration", input.Iteration,
				"paused", paused,
			)

			return MailboxWatcherResult{
				LastProcessedEmails: last.ProcessedEmails,
				Stopped:             false,
			}, workflow.NewContinueAsNewError(ctx, MailboxWatcherWorkflow, MailboxWatcherInput{
				UserID:          input.UserID,
				PollIntervalSec: input.PollIntervalSec,
				Iteration:       0,
			})
		}

		timerCtx, cancelTimer := workflow.WithCancel(ctx)
		timerFuture := workflow.NewTimer(timerCtx, time.Duration(input.PollIntervalSec)*time.Second)

		wokeBySignal := false
		stopped := false

		selector := workflow.NewSelector(ctx)
		selector.AddFuture(timerFuture, func(f workflow.Future) {
			_ = f.Get(ctx, nil)
		})
		selector.AddReceive(stopCh, func(c workflow.ReceiveChannel, more bool) {
			c.Receive(ctx, nil)
			wokeBySignal = true
			stopped = true
			cancelTimer()
			logger.Info("mailbox watcher received stop signal during sleep",
				"user_id", input.UserID,
				"iteration", input.Iteration,
			)
		})
		selector.AddReceive(pauseCh, func(c workflow.ReceiveChannel, more bool) {
			c.Receive(ctx, nil)
			wokeBySignal = true
			paused = true
			cancelTimer()
			logger.Info("mailbox watcher paused during sleep",
				"user_id", input.UserID,
				"iteration", input.Iteration,
			)
		})
		selector.AddReceive(resumeCh, func(c workflow.ReceiveChannel, more bool) {
			c.Receive(ctx, nil)
			wokeBySignal = true
			cancelTimer()
			logger.Info("mailbox watcher received resume signal while not paused",
				"user_id", input.UserID,
				"iteration", input.Iteration,
			)
		})

		selector.Select(ctx)

		if stopped {
			return MailboxWatcherResult{
				LastProcessedEmails: last.ProcessedEmails,
				Stopped:             true,
			}, nil
		}

		if wokeBySignal {
			if drainSignals() {
				return MailboxWatcherResult{
					LastProcessedEmails: last.ProcessedEmails,
					Stopped:             true,
				}, nil
			}
			continue
		}
	}
}