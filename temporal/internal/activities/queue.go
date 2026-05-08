package activities

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"

	"github.com/joho/godotenv"
	"go.temporal.io/sdk/activity"

	"OrdersAgent/storage/api"
	"OrdersAgent/storage/configdb"
)

// QueueActivities хранит доступ к DB API
type QueueActivities struct {
	DB *api.DB
}

// QueueItemDTO — упрощённый view записи очереди для workflow (item-level)
// type QueueItemDTO struct {
// 	ID           int64
// 	TargetUserID int64
// 	EmailUID     *int64
// 	ObjectBucket *string
// 	ObjectKey    *string
// 	Status       string
// }

// EmailGroupDTO — агрегированное представление письма (email_uid-level)
type EmailGroupDTO struct {
	EmailUID     int64
	TargetUserID int64
	Subject      string
	Body         string
	FilesText    string
}

// LLMResultDTO — результат классификации одного письма
type LLMResultDTO struct {
	Prob1          float64 `json:"prob_1"`
	PredictedClass *int16  `json:"predicted_class"`
	ModelDecision  string  `json:"model_decision"`
}

// NewQueueActivities инициализирует подключение к БД
func NewQueueActivities() (*QueueActivities, error) {
	// Явно грузим storage/.env
	if err := godotenv.Load("storage/.env"); err != nil {
		return nil, fmt.Errorf("load storage/.env: %w", err)
	}

	cfg := configdb.FromEnv()
	db, err := api.ConnectPostgres(cfg)
	if err != nil {
		return nil, fmt.Errorf("connect db: %w", err)
	}
	return &QueueActivities{DB: db}, nil
}

// =====================
// Старые item-level activity
// =====================

// func (a *QueueActivities) GetQueueItemActivity(ctx context.Context, id int64) (*QueueItemDTO, error) {
// 	activity.GetLogger(ctx).Info("GetQueueItemActivity called", "id", id)

// 	item, err := a.DB.GetQueueItemByID(ctx, id)
// 	if err != nil {
// 		return nil, fmt.Errorf("get queue item %d: %w", id, err)
// 	}

// 	return &QueueItemDTO{
// 		ID:           item.ID,
// 		TargetUserID: item.TargetUserID,
// 		EmailUID:     item.EmailUID,
// 		ObjectBucket: item.ObjectBucket,
// 		ObjectKey:    item.ObjectKey,
// 		Status:       item.Status,
// 	}, nil
// }

// func (a *QueueActivities) SetStatusActivity(ctx context.Context, id int64, status string) error {
// 	activity.GetLogger(ctx).Info("SetStatusActivity called", "id", id, "status", status)

// 	if err := a.DB.UpdateQueueItemStatus(ctx, id, status); err != nil {
// 		return fmt.Errorf("update status for %d: %w", id, err)
// 	}
// 	return nil
// }

// =====================
// Новые email-level activity
// =====================

func (a *QueueActivities) SetEmailStatusActivity(ctx context.Context, emailUID int64, status string) error {
	activity.GetLogger(ctx).Info("SetEmailStatusActivity called", "email_uid", emailUID, "status", status)

	if err := a.DB.UpdateQueueStatusByEmailUID(ctx, emailUID, status); err != nil {
		return fmt.Errorf("update status for email_uid=%d: %w", emailUID, err)
	}
	return nil
}

func (a *QueueActivities) GetEmailGroupActivity(ctx context.Context, emailUID int64) (*EmailGroupDTO, error) {
	activity.GetLogger(ctx).Info("GetEmailGroupActivity called", "email_uid", emailUID)

	eg, err := a.DB.GetEmailGroupByUID(ctx, emailUID)
	if err != nil {
		return nil, fmt.Errorf("get email group email_uid=%d: %w", emailUID, err)
	}

	return &EmailGroupDTO{
		EmailUID:     eg.EmailUID,
		TargetUserID: eg.TargetUserID,
		Subject:      eg.Subject,
		Body:         eg.Body,
		FilesText:    eg.FilesText,
	}, nil
}

func (a *QueueActivities) RunLLMActivity(ctx context.Context, email *EmailGroupDTO) (*LLMResultDTO, error) {
	logger := activity.GetLogger(ctx)
	logger.Info("RunLLMActivity called", "email_uid", email.EmailUID)

	payload := map[string]any{
		"subject":    email.Subject,
		"body":       email.Body,
		"files_text": email.FilesText,
	}

	inputBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal LLM payload: %w", err)
	}

	cmd := exec.CommandContext(ctx, "uv", "run", "python", "classify_one.py")
	cmd.Dir = "llm_worker"

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("open stdin for LLM: %w", err)
	}

	go func() {
		defer stdin.Close()
		_, _ = stdin.Write(inputBytes)
	}()

	if err := cmd.Run(); err != nil {
		logger.Error("RunLLMActivity python error", "stderr", stderr.String())
		return nil, fmt.Errorf("run LLM python: %w", err)
	}

	outStr := stdout.String()

	// Берём последнюю непустую строку
	lines := bytes.Split(stdout.Bytes(), []byte("\n"))
	var last []byte
	for i := len(lines) - 1; i >= 0; i-- {
		if len(bytes.TrimSpace(lines[i])) > 0 {
			last = lines[i]
			break
		}
	}

	if last == nil {
		logger.Error("RunLLMActivity json parse error", "stdout", outStr)
		return nil, fmt.Errorf("unmarshal LLM result: no non-empty lines in stdout")
	}

	var res LLMResultDTO
	if err := json.Unmarshal(last, &res); err != nil {
		logger.Error("RunLLMActivity json parse error", "stdout", outStr, "json_line", string(last))
		return nil, fmt.Errorf("unmarshal LLM result: %w", err)
	}

	logger.Info("RunLLMActivity result",
		"prob_1", res.Prob1,
		"predicted_class", res.PredictedClass,
		"model_decision", res.ModelDecision,
	)

	return &res, nil
}

func (a *QueueActivities) SaveClassificationActivity(ctx context.Context, emailUID int64, res *LLMResultDTO) error {
	activity.GetLogger(ctx).Info("SaveClassificationActivity called",
		"email_uid", emailUID,
		"prob_1", res.Prob1,
		"predicted_class", res.PredictedClass,
		"model_decision", res.ModelDecision,
	)

	if err := a.DB.UpdateClassificationByEmailUID(ctx, emailUID, res.Prob1, res.PredictedClass, res.ModelDecision); err != nil {
		return fmt.Errorf("update classification email_uid=%d: %w", emailUID, err)
	}
	return nil
}

func (a *QueueActivities) EnqueueFilesProcessingActivity(ctx context.Context, emailUID int64) error {
	logger := activity.GetLogger(ctx)
	logger.Info("EnqueueFilesProcessingActivity called",
		"email_uid", emailUID,
	)

	items, err := a.DB.GetEmailFilesByUID(ctx, emailUID)
	if err != nil {
		return fmt.Errorf("get files for email_uid=%d: %w", emailUID, err)
	}

	if len(items) == 0 {
		logger.Info("no files found for email_uid",
			"email_uid", emailUID,
		)
		return nil
	}

	for _, it := range items {
		logger.Info("file prepared for processing-files-queue",
			"queue_id", it.ID,
			"email_uid", emailUID,
			"document_name", it.DocName,
			"object_bucket", it.ObjectBucket,
			"object_key", it.ObjectKey,
		)

		// TODO: когда будет готов table_worker:
		// здесь отправить сообщение в processing-files-queue
		// с использованием it.ObjectBucket, it.ObjectKey, it.DocName.
	}

	return nil
}