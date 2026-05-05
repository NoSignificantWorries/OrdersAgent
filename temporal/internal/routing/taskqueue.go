package routing

import "fmt"

// WorkflowQueue возвращает имя очереди для workflow'ов конкретного менеджера
func WorkflowQueue(targetUserID int64) string {
    return fmt.Sprintf("manager-%d-orchestrator", targetUserID)
}

// ActivityQueue возвращает имя очереди для тяжёлых activity конкретного менеджера
func ActivityQueue(targetUserID int64) string {
    return fmt.Sprintf("manager-%d-documents", targetUserID)
}