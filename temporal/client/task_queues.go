package client

import "fmt"

// Общая очередь для обработки писем (ProcessEmailWorkflow).
const EmailProcessingTaskQueue = "emails-processing"

// Очередь для watcher/polling почты конкретного менеджера (userID).
func MailboxSyncTaskQueue(userID int64) string {
	return fmt.Sprintf("manager-%d-mailbox-sync", userID)
}