package contracts

import "fmt"

const (
	ProcessEmailWorkflowName = "ProcessEmailWorkflow"
	EmailProcessingTaskQueue = "emails-processing"
)

type ProcessEmailInput struct {
	EmailUID     int64 `json:"email_uid"`
	TargetUserID int64 `json:"target_user_id"`
}

func EmailWorkflowID(userID, emailUID int64) string {
	return fmt.Sprintf("manager-%d-email-%d", userID, emailUID)
}